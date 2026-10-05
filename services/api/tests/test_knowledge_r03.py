"""R0.3 release tests: authorized text knowledge and protocol-bound answers."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, select, text

from symsoil_api.cli import initialize_synthetic_documents, seed_demo
from symsoil_api.main import create_app
from symsoil_api.models import Document, KnowledgeAudience, KnowledgeDocument, KnowledgeReview, KnowledgeRevision, User
from symsoil_api.ollama import OllamaAdapter
from symsoil_api.security import stamp, utcnow

P = "/api/v1"


def fields(**changes):
    return {"title": "合成清理规则", "category": "开发样本", "body": "合成清理工具需要核实。\n清理负责人须本人接受。", "source": "明确合成文本来源", "rights": "仅开发测试授权", "purpose": "清理关键词与原文引用开发", "maintainer": "合成维护人", "effective_until": None, "requested_scope": "community", "requested_member_ids": [], **changes}


def post(client, path, data, key=None):
    return client.post(P + path, content=json.dumps(data, ensure_ascii=True), headers={"Idempotency-Key": key or str(uuid4()), "Content-Type": "application/json"})


def publish(harness, **changes):
    app, ids, login = harness
    author, reviewer = login("qiao"), login("lin")
    created = post(author, "/knowledge", fields(**changes)).json()
    submitted = post(author, f"/knowledge/{created['id']}/submit", {"object_version": created["version"], "revision_id": created["latest"]["id"], "reviewer_id": ids["lin"], "consent": True}).json()
    response = post(reviewer, f"/knowledge/{created['id']}/review", {"object_version": submitted["version"], "revision_id": submitted["latest"]["id"], "decision": "approve", "reason": "开发测试的合成审核"})
    assert response.status_code == 200, response.text
    detail = author.get(P + f"/knowledge/{created['id']}").json()
    return author, reviewer, detail


def test_private_revisions_never_write_snapshot(harness):
    app, _ids, login = harness
    owner, admin = login("qiao"), login("admin")
    first = post(owner, "/knowledge", fields()).json()
    with app.state.session_factory() as db:
        assert db.get(Document, first["id"]) is None
    next_version = owner.patch(P + f"/knowledge/{first['id']}", json={"object_version": first["version"], **fields(body="第二版私人正文")}).json()
    assert next_version["latest"]["number"] == 2
    assert admin.get(P + f"/knowledge/{first['id']}").status_code == 404
    assert all(item["id"] != first["id"] for item in admin.get(P + "/documents").json())
    with app.state.session_factory() as db:
        assert db.get(KnowledgeRevision, first["latest"]["id"]).body == first["latest"]["body"]
        assert db.get(Document, first["id"]) is None


def test_submit_requires_actual_boolean_consent(harness):
    _app, ids, login = harness
    author = login("qiao")
    doc = post(author, "/knowledge", fields()).json()
    body = {"object_version": 1, "revision_id": doc["latest"]["id"], "reviewer_id": ids["lin"], "consent": 1}
    assert post(author, f"/knowledge/{doc['id']}/submit", body).status_code == 422
    assert author.get(P + f"/knowledge/{doc['id']}").json()["submitted"] is None


def test_review_rejection_and_no_self_review(harness):
    _app, ids, login = harness
    facilitator = login("lin")
    doc = post(facilitator, "/knowledge", fields()).json()
    self_submit = post(facilitator, f"/knowledge/{doc['id']}/submit", {"object_version": 1, "revision_id": doc["latest"]["id"], "reviewer_id": ids["lin"], "consent": True})
    assert self_submit.status_code == 422
    doc = post(facilitator, f"/knowledge/{doc['id']}/submit", {"object_version": 1, "revision_id": doc["latest"]["id"], "reviewer_id": ids["admin"], "consent": True}).json()
    admin = login("admin")
    invalid = post(admin, f"/knowledge/{doc['id']}/review", {"object_version": doc["version"], "revision_id": doc["latest"]["id"], "decision": "changes_requested", "reason": " "})
    assert invalid.status_code == 422
    assert post(admin, f"/knowledge/{doc['id']}/review", {"object_version": doc["version"], "revision_id": doc["latest"]["id"], "decision": "changes_requested", "reason": "请补充资料许可"}).status_code == 200
    current = facilitator.get(P + f"/knowledge/{doc['id']}").json()
    assert current["submitted"] is None and current["published"] is None
    assert current["reviews"][-1]["reason"] == "请补充资料许可"
    assert admin.get(P + "/knowledge/reviews").json() == []


def test_edit_cancels_review_and_keeps_previous_published_body(harness):
    author, reviewer, doc = publish(harness)
    old_revision = doc["published"]["id"]
    edited = author.patch(P + f"/knowledge/{doc['id']}", json={"object_version": doc["version"], **fields(body="第二版清理范围尚需核实")}).json()
    submitted = post(author, f"/knowledge/{doc['id']}/submit", {"object_version": edited["version"], "revision_id": edited["latest"]["id"], "reviewer_id": doc["reviews"][-1]["reviewer_id"], "consent": True}).json()
    before = reviewer.get(P + "/knowledge/reviews").json()
    assert before[0]["revision"]["body"] == edited["latest"]["body"]
    next_version = author.patch(P + f"/knowledge/{doc['id']}", json={"object_version": submitted["version"], **fields(body="第三版私人未送审")}).json()
    assert reviewer.get(P + "/knowledge/reviews").json() == []
    assert post(reviewer, f"/knowledge/{doc['id']}/review", {"object_version": submitted["version"], "revision_id": edited["latest"]["id"], "decision": "approve", "reason": ""}).status_code == 404
    public = reviewer.get(P + f"/documents/{doc['id']}").json()
    assert public["revision_id"] == old_revision and public["body"] == doc["published"]["body"]
    assert next_version["published"]["id"] == old_revision


def test_cancel_submission_replay_does_not_restart_review(harness):
    _app, ids, login = harness
    author, reviewer = login("qiao"), login("lin")
    doc = post(author, "/knowledge", fields()).json()
    submit_body = {"object_version": 1, "revision_id": doc["latest"]["id"], "reviewer_id": ids["lin"], "consent": True}
    doc = post(author, f"/knowledge/{doc['id']}/submit", submit_body, "submit-once").json()
    cancelled = post(author, f"/knowledge/{doc['id']}/cancel-submission", {"object_version": doc["version"]}, "cancel-once").json()
    assert cancelled["submitted"] is None
    replayed = post(author, f"/knowledge/{doc['id']}/submit", submit_body, "submit-once").json()
    assert replayed["version"] == cancelled["version"] and replayed["submitted"] is None
    assert reviewer.get(P + "/knowledge/reviews").json() == []


def test_literal_keyword_and_exact_snippet_coordinates(harness):
    author, _reviewer, doc = publish(harness, body="第一行\r\n清理%_工具必须核实。\r\n末行")
    matched = author.get(P + "/documents", params={"q": "%_"}).json()
    assert [item["id"] for item in matched] == [doc["id"]]
    fragment = matched[0]["snippets"][0]
    assert fragment["quote"] == "清理%_工具必须核实。" and fragment["start_line"] == fragment["end_line"] == 2
    assert author.get(P + "/documents", params={"q": "不存在_%"}).json() == []
    answer = post(author, "/knowledge/answers", {"question": "清理工具", "use_model": False}).json()
    assert answer["mode"] == "extract" and "非模型回答" in answer["answer"]
    assert any(item["document_id"] == doc["id"] and item["quote"] in doc["published"]["body"] for item in answer["citations"])


def test_expiry_is_server_driven_and_no_reapproval(harness):
    app, _ids, login = harness
    author, reviewer, doc = publish(harness, effective_until=stamp(utcnow() + timedelta(hours=1)))
    with app.state.session_factory() as db:
        # Test-only fixture clock shift; public API never modifies revisions.
        revision = db.get(KnowledgeRevision, doc["published"]["id"])
        revision.effective_until = stamp(utcnow() - timedelta(seconds=1))
        db.commit()
    assert reviewer.get(P + f"/documents/{doc['id']}").status_code == 404
    detail = author.get(P + f"/knowledge/{doc['id']}").json()
    assert detail["publication_active"] is False and detail["audience"] is None
    assert detail["published"]["id"] == doc["published"]["id"]
    assert post(author, f"/knowledge/{doc['id']}/restrict", {"object_version": doc["version"], "scope": "members", "member_ids": []}).status_code == 422
    expired = post(author, "/knowledge", fields(effective_until=stamp(utcnow() - timedelta(hours=1)))).json()
    submitted = post(author, f"/knowledge/{expired['id']}/submit", {"object_version": 1, "revision_id": expired["latest"]["id"], "reviewer_id": doc["reviews"][-1]["reviewer_id"], "consent": True}).json()
    assert post(reviewer, f"/knowledge/{expired['id']}/review", {"object_version": submitted["version"], "revision_id": submitted["latest"]["id"], "decision": "approve", "reason": ""}).status_code == 422


@pytest.mark.parametrize("changes", [
    {"body": "bad\u0000binary"}, {"body": "bad\ud800surrogate"}, {"source": "bad\u0001control"}, {"effective_until": "2026-10-05T12:00:00"},
    {"requested_scope": "community", "requested_member_ids": ["nonmember"]}, {"requested_scope": "members", "requested_member_ids": []},
    {"requested_scope": "members", "requested_member_ids": ["unknown-member"]}, {"owner_id": "forged"},
])
def test_strict_text_and_acl_fields(harness, changes):
    _app, _ids, login = harness
    response = post(login("qiao"), "/knowledge", fields(**changes))
    assert response.status_code == 422
    assert "bad" not in response.text and "forged" not in response.text


def test_explicit_migration_preserves_and_quarantines_legacy_rows(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'legacy.db'}")
    with app.state.session_factory() as db:
        seed_demo(db, "only-test-password-2026")
        preserved_users = list(db.scalars(select(User.id)))
        known_ids = list(db.scalars(select(Document.id)))
        # Simulate the actual pre-R03 schema, leaving every original table/row.
        for table in (KnowledgeReview, KnowledgeAudience, KnowledgeRevision, KnowledgeDocument):
            db.execute(text(f"DROP TABLE {table.__tablename__}"))
        db.add(Document(id="legacy-unknown", title="私人真实资料不可擅自批准", category="隔离", body="不能自动发布的旧正文", source="未知来源", version=1, updated_at=stamp()))
        db.commit()
    app.state.engine.dispose()
    next_app = create_app(f"sqlite:///{tmp_path / 'legacy.db'}")
    with next_app.state.session_factory() as db:
        assert not list(db.scalars(select(KnowledgeDocument.id)))
        assert set(db.scalars(select(User.id))) == set(preserved_users)
        assert initialize_synthetic_documents(db) == 3
        db.commit()
        assert initialize_synthetic_documents(db) == 0
        assert set(db.scalars(select(KnowledgeDocument.id))) == set(known_ids)
        assert db.get(Document, "legacy-unknown").body == "不能自动发布的旧正文"
        assert db.get(KnowledgeDocument, "legacy-unknown") is None
        assert len(inspect(db.connection()).get_table_names()) >= 20
    next_app.state.engine.dispose()


def configured_adapter(monkeypatch, transport):
    monkeypatch.setenv("SYMSOIL_AI_ENABLED", "true")
    monkeypatch.setenv("SYMSOIL_OLLAMA_MODEL", "synthetic-test:latest")
    return OllamaAdapter(transport=httpx.MockTransport(transport))


def model_transport(output, captured=None):
    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "synthetic-test:latest"}]})
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        data = json.loads(payload["messages"][1]["content"])
        if captured is not None:
            captured.append(data)
        result = output(data) if callable(output) else output
        return httpx.Response(200, json={"done": True, "message": {"role": "assistant", "content": json.dumps(result)}})
    return handle


def test_model_uses_only_authorized_server_fragments(harness, monkeypatch):
    app, ids, login = harness
    author, _reviewer, doc = publish(harness)
    secret_author, _secret_reviewer, secret = publish(harness, title="不准管理员看的秘密资料", body="清理秘密 PRIVATE-CANARY", requested_scope="members", requested_member_ids=[ids["lin"]])
    admin = login("admin")
    captured = []
    adapter = configured_adapter(monkeypatch, model_transport(lambda data: {"answer": "合成协议输出：需核实清理工具。", "citation_ids": [data["sources"][0]["citation_id"]]}, captured))
    app.state.ollama = adapter
    answer = post(admin, "/knowledge/answers", {"question": "清理", "use_model": True})
    assert answer.status_code == 200, answer.text
    assert answer.json()["mode"] == "local_model"
    assert "PRIVATE-CANARY" not in json.dumps(captured, ensure_ascii=False)
    assert all(set(source) == {"citation_id", "title", "source", "quote"} for source in captured[0]["sources"])
    assert all(item["document_id"] != secret["id"] for item in answer.json()["citations"])
    with app.state.session_factory() as db:
        assert not db.scalar(select(KnowledgeReview.id).where(KnowledgeReview.reason.contains("协议输出")))


@pytest.mark.parametrize("output", [
    {"answer": "bad\ud800surrogate", "citation_ids": ["unknown"]},
    {"answer": "伪造引用", "citation_ids": ["https://attacker.example/fake"]},
    {"answer": "未引用回答", "citation_ids": []},
    {"answer": "重复引用", "citation_ids": ["same", "same"]},
    {"answer": "越权字段", "citation_ids": [], "url": "https://attacker.example"},
])
def test_invalid_model_citations_fail_closed(harness, monkeypatch, output):
    app, _ids, login = harness
    publish(harness)
    app.state.ollama = configured_adapter(monkeypatch, model_transport(output))
    answer = post(login("admin"), "/knowledge/answers", {"question": "清理", "use_model": True})
    assert answer.status_code == 503 and "伪造" not in answer.text and "attacker" not in answer.text


def test_model_off_keeps_manual_excerpt_and_no_sources_skips_model(harness):
    app, _ids, login = harness
    reader = login("admin")
    assert post(reader, "/knowledge/answers", {"question": "清理", "use_model": False}).json()["mode"] == "extract"
    assert post(reader, "/knowledge/answers", {"question": "清理", "use_model": True}).status_code == 503
    assert post(reader, "/knowledge/answers", {"question": "不存在123456789", "use_model": True}).json()["mode"] == "insufficient"


@pytest.mark.parametrize("change", ["withdraw", "restrict", "freeze"])
def test_generation_rechecks_source_and_account(harness, monkeypatch, change):
    app, ids, login = harness
    author, _reviewer, doc = publish(harness)
    reader, admin = login("lin"), login("admin")
    started, release = Event(), Event()

    def generated(data):
        started.set()
        assert release.wait(5)
        return {"answer": "合成协议回答", "citation_ids": [item["citation_id"] for item in data["sources"][:1]]}

    app.state.ollama = configured_adapter(monkeypatch, model_transport(generated))
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(post, reader, "/knowledge/answers", {"question": "清理", "use_model": True})
        assert started.wait(3)
        if change == "freeze":
            response = post(admin, f"/admin/members/{ids['lin']}/freeze", {})
        elif change == "restrict":
            response = post(author, f"/knowledge/{doc['id']}/restrict", {"object_version": doc["version"], "scope": "members", "member_ids": []})
        else:
            response = post(author, f"/knowledge/{doc['id']}/withdraw", {"object_version": doc["version"]})
        assert response.status_code == 200, response.text
        release.set()
        result = future.result(timeout=5)
    assert result.status_code == (401 if change == "freeze" else 409)
    assert "合成协议回答" not in result.text and "清理工具" not in result.text


def test_same_gate_covers_expression_and_knowledge(monkeypatch):
    adapter = configured_adapter(monkeypatch, model_transport({"answer": "", "citation_ids": []}))
    assert adapter.gate.acquire(False)
    try:
        with pytest.raises(HTTPException) as error:
            adapter.answers("清理", [])
        assert error.value.status_code == 429
        with pytest.raises(HTTPException) as error:
            adapter.suggestions("原话", "", "", "")
        assert error.value.status_code == 429
    finally:
        adapter.gate.release()


@pytest.mark.parametrize("change", ["restrict", "withdraw"])
def test_approved_revision_cannot_restore_old_publication_scope(harness, change):
    _app, ids, _login = harness
    author, reviewer, doc = publish(harness)
    if change == "restrict":
        narrowed = post(author, f"/knowledge/{doc['id']}/restrict", {"object_version": doc["version"], "scope": "members", "member_ids": []}).json()
    else:
        narrowed = post(author, f"/knowledge/{doc['id']}/withdraw", {"object_version": doc["version"]}).json()
    request = {"object_version": narrowed["version"], "revision_id": narrowed["latest"]["id"], "reviewer_id": ids["lin"], "consent": True}
    rejected = post(author, f"/knowledge/{doc['id']}/submit", request)
    assert rejected.status_code == 409
    assert reviewer.get(P + f"/documents/{doc['id']}").status_code == 404
    assert reviewer.get(P + "/knowledge/reviews").json() == []
    # Saving a complete new revision is a distinct step before broader review.
    new_version = author.patch(P + f"/knowledge/{doc['id']}", json={"object_version": narrowed["version"], **fields()}).json()
    new_request = {**request, "object_version": new_version["version"], "revision_id": new_version["latest"]["id"]}
    assert post(author, f"/knowledge/{doc['id']}/submit", new_request).status_code == 200


def test_private_edit_does_not_change_publication_timestamp(harness):
    author, reviewer, doc = publish(harness)
    before = reviewer.get(P + f"/documents/{doc['id']}").json()
    author.patch(P + f"/knowledge/{doc['id']}", json={"object_version": doc["version"], **fields(body="另存尚未公开的正文")})
    after = reviewer.get(P + f"/documents/{doc['id']}").json()
    assert after["updated_at"] == before["updated_at"]
    assert after["revision_id"] == before["revision_id"]


def test_inconsistent_snapshot_is_quarantined_from_every_public_path(harness):
    app, _ids, login = harness
    author, reviewer, doc = publish(harness, title="UNIQUE-CORRUPT-SNAPSHOT", body="唯一隔离镜像关键词xyzzy")
    initial_count = reviewer.get(P + "/dashboard").json()["counts"]["documents"]
    with app.state.session_factory() as db:
        db.get(Document, doc["id"]).body = "异常外部修改，不是获准资料"
        db.commit()
    assert reviewer.get(P + f"/documents/{doc['id']}").status_code == 404
    assert reviewer.get(P + "/documents", params={"q": "UNIQUE-CORRUPT-SNAPSHOT"}).json() == []
    assert reviewer.get(P + "/dashboard").json()["counts"]["documents"] == initial_count - 1
    answer = post(reviewer, "/knowledge/answers", {"question": "xyzzy", "use_model": False}).json()
    assert answer["mode"] == "insufficient" and answer["citations"] == []
    assert author.get(P + f"/knowledge/{doc['id']}").json()["publication_active"] is False
