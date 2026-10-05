import json
import stat

import pytest
from fastapi.testclient import TestClient

from symsoil_api.main import create_app
from symsoil_api.models import RecoveryPending, RecoveryState, Session, User
from symsoil_api.recovery import GENESIS


def test_restrictive_event_advances_independent_watermark_without_private_text(harness):
    app, _ids, login = harness
    author = login("qiao")
    secret = "R05-SECRET-PRIVATE-TEXT-NEVER-JOURNAL"

    created = author.post("/api/v1/utterances", json={"title": "私稿", "text": secret})
    assert created.status_code == 200
    item = created.json()
    assert app.state.recovery.journal.read_text(encoding="utf-8") == ""

    changed = author.patch(
        f"/api/v1/utterances/{item['id']}",
        json={"title": "仍是私稿", "text": secret + "-changed", "object_version": 1},
    )
    assert changed.status_code == 200
    assert app.state.recovery.journal.read_text(encoding="utf-8") == ""

    topic_id = author.get("/api/v1/topics").json()[0]["id"]
    confirmed = author.post(
        f"/api/v1/utterances/{item['id']}/confirmations",
        json={"object_version": 2},
        headers={"Idempotency-Key": "r05-confirm"},
    )
    assert confirmed.status_code == 200
    shared = author.post(
        f"/api/v1/utterances/{item['id']}/share",
        json={"object_version": 2, "topic_id": topic_id, "representation": "original"},
        headers={"Idempotency-Key": "r05-share"},
    )
    assert shared.status_code == 200
    revoked = author.post(
        f"/api/v1/utterances/{item['id']}/revoke",
        json={"object_version": 2},
    )
    assert revoked.status_code == 200

    lines = app.state.recovery.journal.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    witness = json.loads(app.state.recovery.witness.read_text(encoding="utf-8"))
    assert event["action"] == "utterance.revoke"
    assert event["sequence"] == witness["sequence"] == 1
    assert event["hash"] == witness["chain_hash"]
    assert secret not in lines[0]
    for directory in (app.state.recovery.journal_dir, app.state.recovery.witness_dir):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for file in (app.state.recovery.journal, app.state.recovery.witness, app.state.recovery.lock):
        assert stat.S_IMODE(file.stat().st_mode) == 0o600

    with app.state.session_factory() as db:
        state = db.get(RecoveryState, "singleton")
        assert (state.sequence, state.chain_hash, state.isolated) == (1, event["hash"], False)
        assert db.query(RecoveryPending).count() == 0


def test_external_failure_keeps_restriction_and_isolates_all_database_routes(harness, monkeypatch):
    app, ids, login = harness
    admin = login("admin")
    member = login("qiao")

    def unavailable(*_args, **_kwargs):
        raise OSError("synthetic unavailable volume")

    monkeypatch.setattr(app.state.recovery, "_persist_events", unavailable)
    response = admin.post(f"/api/v1/admin/members/{ids['qiao']}/freeze")
    assert response.status_code == 503
    assert "服务保持隔离" in response.json()["detail"]

    with app.state.session_factory() as db:
        assert db.get(User, ids["qiao"]).active is False
        sessions = list(db.query(Session).filter(Session.user_id == ids["qiao"]))
        assert sessions and all(item.revoked for item in sessions)
        state = db.get(RecoveryState, "singleton")
        assert state.isolated is True and state.sequence == 0
        pending = db.query(RecoveryPending).one()
        assert pending.action == "member.freeze"

    assert app.state.recovery.journal.read_text(encoding="utf-8") == ""
    assert admin.get("/api/v1/admin/members").status_code == 503
    assert member.get("/api/v1/utterances").status_code == 503
    assert admin.get("/api/v1/ready").status_code == 503
    fresh = TestClient(app)
    try:
        assert fresh.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "only-test-password-2026"},
        ).status_code == 503
        assert fresh.get("/api/v1/health").status_code == 200
    finally:
        fresh.close()


@pytest.mark.parametrize("target", ["journal", "witness"])
def test_tampered_external_recovery_medium_fails_closed(harness, target):
    app, ids, login = harness
    admin = login("admin")
    assert admin.post(f"/api/v1/admin/members/{ids['qiao']}/freeze").status_code == 200

    path = getattr(app.state.recovery, target)
    path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    response = admin.get("/api/v1/admin/members")
    assert response.status_code == 503


def test_world_readable_recovery_medium_fails_closed(harness):
    app, _ids, login = harness
    admin = login("admin")
    app.state.recovery.journal.chmod(0o644)
    response = admin.get("/api/v1/admin/members")
    assert response.status_code == 503
    assert "权限过宽" in response.json()["detail"]


def test_confirmed_watermark_survives_application_restart(harness):
    app, ids, login = harness
    admin = login("admin")
    assert admin.post(f"/api/v1/admin/members/{ids['qiao']}/freeze").status_code == 200
    database_url = str(app.state.engine.url)

    reopened = create_app(database_url)
    client = TestClient(reopened)
    try:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "only-test-password-2026"},
        )
        assert response.status_code == 200
        assert client.get("/api/v1/ready").json() == {"status": "ready"}
        assert reopened.state.recovery._read_witness()["sequence"] == 1
    finally:
        client.close()
        reopened.state.engine.dispose()


def test_business_watermark_rollback_cannot_revive_access(harness):
    app, ids, login = harness
    admin = login("admin")
    assert admin.post(f"/api/v1/admin/members/{ids['qiao']}/freeze").status_code == 200

    with app.state.session_factory() as db:
        state = db.get(RecoveryState, "singleton")
        state.sequence = 0
        state.chain_hash = GENESIS
        db.commit()

    response = admin.get("/api/v1/admin/members")
    assert response.status_code == 503
    assert "不一致" in response.json()["detail"]
