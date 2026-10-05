"""Fail-closed revocation journal for the current SQLite development node.

The journal deliberately contains identifiers and restrictive state only.  It
is independent from the business database and is never a general audit export.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

from .models import (
    ExpressionCandidate,
    KnowledgeAudience,
    KnowledgeCorrection,
    KnowledgeDocument,
    RecoveryPending,
    RecoveryState,
    User,
    Utterance,
)
from .security import stamp


GENESIS = "0" * 64
RESTRICTIONS = {
    "member.freeze",
    "utterance.edit",
    "utterance.revoke",
    "expression.candidate.edit",
    "expression.choice",
    "knowledge.cancel_submission",
    "knowledge.withdraw",
    "knowledge.restrict",
    "correction.withdraw",
}


class RecoveryError(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_hash(previous, event):
    return hashlib.sha256((previous + _canonical(event)).encode()).hexdigest()


class RecoveryStore:
    def __init__(self, engine):
        if engine.dialect.name != "sqlite" or not engine.url.database or engine.url.database == ":memory:":
            raise RecoveryError("当前权限收紧日志仅支持本机文件型 SQLite")
        database = Path(engine.url.database).resolve()
        self.journal_dir = Path(os.getenv("SYMSOIL_REVOCATION_DIR", str(database) + ".revocations")).resolve()
        self.witness_dir = Path(os.getenv("SYMSOIL_RECOVERY_WITNESS_DIR", str(database) + ".witness")).resolve()
        if self.journal_dir == self.witness_dir or self.journal_dir in self.witness_dir.parents or self.witness_dir in self.journal_dir.parents:
            raise RecoveryError("撤权日志和可信水位必须使用互不嵌套的独立目录")
        if database in self.journal_dir.parents or database in self.witness_dir.parents:
            raise RecoveryError("撤权日志或可信水位目录配置无效")
        self.journal = self.journal_dir / "revocations.jsonl"
        self.witness = self.witness_dir / "watermark.json"
        self.lock = self.journal_dir / ".lock"

    def initialize(self, factory):
        self.journal_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.witness_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.journal_dir, 0o700)
        os.chmod(self.witness_dir, 0o700)
        with factory() as db:
            state = db.get(RecoveryState, "singleton")
            if state:
                for path in (self.journal, self.witness, self.lock):
                    if path.exists():
                        os.chmod(path, 0o600)
                return
            if self.journal.exists() or self.witness.exists():
                raise RecoveryError("数据库缺少恢复身份，但独立恢复介质已经存在；拒绝覆盖")
            instance_id = str(uuid4())
            self.journal.touch(mode=0o600, exist_ok=False)
            os.chmod(self.journal, 0o600)
            self._fsync_file(self.journal)
            self._write_witness({"instance_id": instance_id, "sequence": 0, "chain_hash": GENESIS})
            db.add(RecoveryState(id="singleton", instance_id=instance_id, sequence=0, chain_hash=GENESIS, isolated=False))
            db.commit()

    def _fsync_file(self, path):
        with path.open("rb") as source:
            os.fsync(source.fileno())

    def _write_witness(self, data):
        temporary = self.witness_dir / (".watermark-" + str(uuid4()))
        try:
            with temporary.open("x", encoding="utf-8") as output:
                os.chmod(temporary, 0o600)
                output.write(_canonical(data) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.witness)
            descriptor = os.open(self.witness_dir, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _read_witness(self):
        try:
            data = json.loads(self.witness.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RecoveryError("可信恢复水位缺失或损坏") from exc
        if set(data) != {"instance_id", "sequence", "chain_hash"} or type(data["sequence"]) is not int:
            raise RecoveryError("可信恢复水位格式无效")
        return data

    def _read_journal(self, instance_id=None):
        sequence, current = 0, GENESIS
        try:
            lines = self.journal.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RecoveryError("独立权限收紧日志不可读取") from exc
        for line in lines:
            try:
                record = json.loads(line)
                digest = record.pop("hash")
            except (ValueError, KeyError) as exc:
                raise RecoveryError("独立权限收紧日志格式无效") from exc
            if (instance_id is not None and record.get("instance_id") != instance_id) or record.get("sequence") != sequence + 1 or record.get("previous_hash") != current or _event_hash(current, record) != digest:
                raise RecoveryError("独立权限收紧日志不连续或已改变")
            sequence, current = record["sequence"], digest
        return sequence, current

    def _assert_private_paths(self):
        try:
            paths = (self.journal_dir, self.witness_dir, self.journal, self.witness)
            if any(path.stat().st_mode & 0o077 for path in paths):
                raise RecoveryError("恢复介质权限过宽，服务保持隔离")
        except OSError as exc:
            raise RecoveryError("恢复介质缺失或不可访问，服务保持隔离") from exc

    def assert_ready(self, db):
        state = db.get(RecoveryState, "singleton")
        if not state or state.isolated or db.scalar(select(RecoveryPending.event_id).limit(1)):
            raise RecoveryError("恢复状态未完成，服务保持隔离")
        self._assert_private_paths()
        witness = self._read_witness()
        sequence, chain_hash = self._read_journal(state.instance_id)
        expected = (state.instance_id, state.sequence, state.chain_hash)
        if expected != (witness.get("instance_id"), witness.get("sequence"), witness.get("chain_hash")) or (sequence, chain_hash) != (state.sequence, state.chain_hash):
            raise RecoveryError("数据库、独立日志与可信水位不一致，服务保持隔离")

    def _payload(self, db, action, object_id):
        if action == "member.freeze":
            item = db.get(User, object_id)
            return {"active": bool(item.active) if item else False}
        if action in {"utterance.edit", "utterance.revoke", "expression.choice"}:
            item = db.get(Utterance, object_id)
            return {"shared_topic_id": item.shared_topic_id if item else None}
        if action == "expression.candidate.edit":
            candidate = db.get(ExpressionCandidate, object_id)
            item = db.get(Utterance, candidate.utterance_id) if candidate else None
            return {"utterance_id": candidate.utterance_id if candidate else None, "shared_topic_id": item.shared_topic_id if item else None}
        if action.startswith("knowledge."):
            item = db.get(KnowledgeDocument, object_id)
            audience = db.get(KnowledgeAudience, object_id)
            return {"withdrawn": bool(item and item.withdrawn_at), "access_epoch": item.access_epoch if item else None, "submitted_revision_id": item.submitted_revision_id if item else None, "reviewer_id": item.reviewer_id if item else None, "scope": audience.scope if audience else None, "member_ids": list(audience.member_ids) if audience else []}
        if action == "correction.withdraw":
            item = db.get(KnowledgeCorrection, object_id)
            return {"status": item.status if item else "withdrawn"}
        return {}

    def queue(self, db, actor_id, action, object_type, object_id, object_version):
        if action not in RESTRICTIONS:
            return
        db.info.setdefault("recovery_events", []).append({"event_id": str(uuid4()), "action": action, "object_type": object_type, "object_id": str(object_id), "actor_id": str(actor_id), "object_version": object_version, "payload": self._payload(db, action, object_id), "created_at": stamp()})

    def _persist_events(self, instance_id, start_sequence, start_hash, events):
        with self.lock.open("a+") as lock:
            os.chmod(self.lock, 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            witness = self._read_witness()
            journal_sequence, journal_hash = self._read_journal(instance_id)
            if (witness["instance_id"], witness["sequence"], witness["chain_hash"]) != (instance_id, start_sequence, start_hash) or (journal_sequence, journal_hash) != (start_sequence, start_hash):
                raise RecoveryError("写入前恢复水位已变化")
            sequence, current = start_sequence, start_hash
            records = []
            for event in events:
                sequence += 1
                record = {"instance_id": instance_id, "sequence": sequence, "previous_hash": current, **event}
                digest = _event_hash(current, record)
                records.append({**record, "hash": digest})
                current = digest
            with self.journal.open("a", encoding="utf-8") as output:
                for record in records:
                    output.write(_canonical(record) + "\n")
                output.flush()
                os.fsync(output.fileno())
            self._write_witness({"instance_id": instance_id, "sequence": sequence, "chain_hash": current})
            return sequence, current

    def commit(self, db):
        events = db.info.pop("recovery_events", [])
        if not events:
            db.commit()
            return
        state = db.get(RecoveryState, "singleton")
        if not state or state.isolated:
            raise RecoveryError("恢复状态未就绪，拒绝提交")
        for event in events:
            db.add(RecoveryPending(**event))
        state.isolated = True
        state.reason = "权限收紧事件等待独立日志确认"
        db.commit()  # The restrictive business mutation is durable before external acknowledgement.
        try:
            sequence, chain_hash = self._persist_events(state.instance_id, state.sequence, state.chain_hash, events)
            state = db.get(RecoveryState, "singleton")
            state.sequence, state.chain_hash = sequence, chain_hash
            state.isolated, state.reason = False, None
            db.execute(delete(RecoveryPending).where(RecoveryPending.event_id.in_([event["event_id"] for event in events])))
            db.commit()
        except Exception as exc:
            db.rollback()
            raise RecoveryError("权限已收紧，但独立日志未完成；服务保持隔离") from exc
