from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from symsoil_api.main import create_app
from symsoil_api.models import Audit, Idempotency, RegistrationInvite, Session, User
from symsoil_api.security import digest, password_hasher, stamp, utcnow


def topic(client):
    return client.get("/api/v1/topics").json()[0]


def original(client, text="这个安排我不能接受，也不会参加。"):
    response = client.post("/api/v1/utterances", json={"title": "我的处境", "text": text})
    assert response.status_code == 200
    return response.json()


def mutation(client, path, data, key="test-key"):
    return client.post("/api/v1" + path, json=data, headers={"Idempotency-Key": key})


def invite(client, topic_id, recipient):
    response = client.post(f"/api/v1/topics/{topic_id}/invitations", json={"invitee_id": recipient, "title": "仅双方可见的邀请", "description": "私密条款", "completion_criteria": "核查清单", "resources": "工具", "compensation": "双方私密商定", "due_date": None})
    assert response.status_code == 200
    return response.json()


def test_login_cookie_hashed_storage_and_safe_session_view(harness):
    app, _ids, login = harness
    client = login("qiao")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookie = client.cookies["symsoil_session"]
    with app.state.session_factory() as db:
        session = db.scalar(select(Session).where(Session.token_hash == digest(cookie)))
        assert session and session.token_hash != cookie
        user = db.get(User, session.user_id)
        assert user.password_hash.startswith("$argon2id$")
    sessions = client.get("/api/v1/auth/sessions").json()
    assert "csrf_token" not in sessions[0] and "token_hash" not in sessions[0]
    unauth = TestClient(app)
    assert unauth.get("/api/v1/dashboard").status_code == 401


def test_csrf_missing_or_wrong_and_cross_origin_blocked(harness):
    _app, _ids, login = harness
    client = login("qiao")
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/utterances", json={"text": "hello", "title": "test"}).status_code == 403
    client.headers["X-CSRF-Token"] = "wrong"
    assert client.post("/api/v1/auth/logout").status_code == 403
    client = login("qiao")
    assert client.post("/api/v1/utterances", json={"text": "hello", "title": "test"}, headers={"Origin": "https://attacker.example"}).status_code == 403


def test_strict_fields_and_actor_impersonation_rejected(harness):
    _app, ids, login = harness
    client = login("qiao")
    response = client.post("/api/v1/utterances", json={"text": "hello", "title": "test", "author_id": ids["lin"]})
    assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert client.post("/api/v1/admin/invites", json={"username": "x", "display_name": "x", "role": "admin"}).status_code == 403
    assert client.post("/api/v1/topics", json={"title": "test", "description": "test", "scope": "test"}).status_code == 403


def test_admin_and_facilitator_cannot_read_or_mutate_private_drafts(harness):
    _app, _ids, login = harness
    author, admin, facilitator = login("qiao"), login("admin"), login("lin")
    item = original(author)
    for caller in (admin, facilitator):
        assert caller.get("/api/v1/utterances").json() == []
        denied = caller.patch(f"/api/v1/utterances/{item['id']}", json={"text": "change", "title": "x", "object_version": 1})
        missing = caller.patch("/api/v1/utterances/missing", json={"text": "change", "title": "x", "object_version": 1})
        assert denied.status_code == missing.status_code == 404
        assert denied.json() == missing.json()
        assert mutation(caller, f"/utterances/{item['id']}/confirmations", {"object_version": 1}).status_code == 404


def test_confirmation_is_distinct_and_unconfirmed_share_fails(harness):
    _app, _ids, login = harness
    client = login("qiao")
    item, discussion = original(client), topic(client)
    assert mutation(client, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": discussion["id"]}).status_code == 422
    response = mutation(client, f"/utterances/{item['id']}/confirmations", {"object_version": 1})
    assert response.json()["confirmed_version"] == 1 and response.json()["shared_topic_id"] is None
    assert client.get(f"/api/v1/topics/{discussion['id']}").json()["viewpoints"] == []


def test_share_exact_original_then_revoke_blocks_current_reads(harness):
    _app, _ids, login = harness
    client, facilitator = login("qiao"), login("lin")
    text = "  这个安排我不能接受，也不会参加。\n请保留我的原话。 "
    item, discussion = original(client, text), topic(client)
    mutation(client, f"/utterances/{item['id']}/confirmations", {"object_version": 1})
    shared = mutation(client, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": discussion["id"]}, "share").json()
    assert shared["text"] == text
    assert facilitator.get(f"/api/v1/topics/{discussion['id']}").json()["viewpoints"][0]["text"] == text
    assert client.post(f"/api/v1/utterances/{item['id']}/revoke", json={"object_version": 1}).status_code == 200
    assert facilitator.get(f"/api/v1/topics/{discussion['id']}").json()["viewpoints"] == []


def test_edit_invalidates_confirmation_sharing_and_rejects_stale_version(harness):
    _app, _ids, login = harness
    client = login("qiao")
    item, discussion = original(client), topic(client)
    mutation(client, f"/utterances/{item['id']}/confirmations", {"object_version": 1})
    mutation(client, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": discussion["id"]}, "share")
    response = client.patch(f"/api/v1/utterances/{item['id']}", json={"title": "新版本", "text": "修改一字。", "object_version": 1})
    assert response.status_code == 200
    assert response.json()["version"] == 2 and response.json()["confirmed_version"] is None and response.json()["shared_topic_id"] is None
    assert client.get(f"/api/v1/topics/{discussion['id']}").json()["viewpoints"] == []
    assert mutation(client, f"/utterances/{item['id']}/confirmations", {"object_version": 1}, "new-key").status_code == 409


def test_confirm_idempotency_replays_once_and_conflicting_payload_fails(harness):
    app, ids, login = harness
    client = login("qiao")
    item = original(client)
    path = f"/utterances/{item['id']}/confirmations"
    first = mutation(client, path, {"object_version": 1}, "same")
    replay = mutation(client, path, {"object_version": 1}, "same")
    assert first.json() == replay.json()
    assert mutation(client, path, {"object_version": 2}, "same").status_code == 409
    with app.state.session_factory() as db:
        events = list(db.scalars(select(Audit).where(Audit.actor_id == ids["qiao"], Audit.action == "utterance.confirm")))
        assert len(events) == 1
    assert client.post("/api/v1" + path, json={"object_version": 1}).status_code == 422


def test_topic_access_is_invited_and_admin_has_no_blanket_topic_access(harness):
    _app, ids, login = harness
    facilitator, member, admin = login("lin"), login("qiao"), login("admin")
    created = facilitator.post("/api/v1/topics", json={"title": "受限议题", "description": "未公开", "scope": "仅受邀者"}).json()
    assert member.get(f"/api/v1/topics/{created['id']}").status_code == 404
    assert admin.get(f"/api/v1/topics/{created['id']}").status_code == 404
    assert created["id"] not in [item["id"] for item in member.get("/api/v1/topics").json()]
    added = facilitator.post(f"/api/v1/topics/{created['id']}/participants", json={"member_id": ids["qiao"], "object_version": 1})
    assert added.status_code == 200 and added.json()["version"] == 2
    assert member.get(f"/api/v1/topics/{created['id']}").status_code == 200
    assert member.post(f"/api/v1/topics/{created['id']}/participants", json={"member_id": ids["admin"], "object_version": 2}).status_code == 404


def test_option_version_and_all_five_stances_no_silent_support(harness):
    _app, _ids, login = harness
    client = login("qiao")
    discussion = topic(client)
    detail = client.get(f"/api/v1/topics/{discussion['id']}").json()
    option = detail["options"][0]
    assert option["stances"] == []
    for index, value in enumerate(("support", "conditional", "reservation", "oppose", "need_info")):
        response = mutation(client, f"/topics/{discussion['id']}/stances", {"option_id": option["id"], "option_version": 1, "stance": value, "condition": "须有工具" if value == "conditional" else ""}, f"stance-{index}")
        assert response.status_code == 200
        saved = next(item for item in response.json()["options"] if item["id"] == option["id"])
        assert len(saved["stances"]) == 1 and saved["stances"][0]["stance"] == value
        assert "approval" not in response.json()
    assert mutation(client, f"/topics/{discussion['id']}/stances", {"option_id": option["id"], "option_version": 2, "stance": "support"}, "stale").status_code == 409


def test_conditional_requires_condition_including_missing_default(harness):
    _app, _ids, login = harness
    client = login("qiao")
    discussion = topic(client)
    option = client.get(f"/api/v1/topics/{discussion['id']}").json()["options"][0]
    body = {"option_id": option["id"], "option_version": 1, "stance": "conditional"}
    assert mutation(client, f"/topics/{discussion['id']}/stances", body).status_code == 422
    body["condition"] = "   "
    assert mutation(client, f"/topics/{discussion['id']}/stances", body).status_code == 422


def test_invitation_terms_only_issuer_recipient_and_not_all_topic_members(harness):
    _app, ids, login = harness
    owner, recipient, third = login("lin"), login("qiao"), login("admin")
    discussion = topic(owner)
    item = invite(owner, discussion["id"], ids["qiao"])
    assert item["id"] in [value["id"] for value in recipient.get("/api/v1/invitations").json()]
    assert third.get("/api/v1/invitations").json() == []
    assert third.get(f"/api/v1/topics/{discussion['id']}").json()["invitations"] == []
    assert mutation(owner, f"/invitations/{item['id']}/response", {"object_version": 1, "response": "accepted"}).status_code == 404


def test_task_invitation_independent_from_topic_access_and_acceptance(harness):
    _app, ids, login = harness
    owner, recipient = login("lin"), login("qiao")
    discussion = owner.post("/api/v1/topics", json={"title": "仅主持人", "description": "受限", "scope": "文字邀请独立"}).json()
    item = invite(owner, discussion["id"], ids["qiao"])
    response = mutation(recipient, f"/invitations/{item['id']}/response", {"object_version": 1, "response": "accepted"})
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    assert recipient.get(f"/api/v1/topics/{discussion['id']}").status_code == 404
    assert response.json()["synthetic"] is True


def test_invitation_response_idempotent_no_duplicate_acceptance(harness):
    app, ids, login = harness
    owner, recipient = login("lin"), login("qiao")
    item = invite(owner, topic(owner)["id"], ids["qiao"])
    path, data = f"/invitations/{item['id']}/response", {"object_version": 1, "response": "accepted", "note": "同意这些合成条款"}
    first, replay = mutation(recipient, path, data, "accept"), mutation(recipient, path, data, "accept")
    assert first.json() == replay.json() and first.json()["version"] == 2
    assert mutation(recipient, path, {**data, "response": "declined"}, "accept").status_code == 409
    assert mutation(recipient, path, {"object_version": 2, "response": "declined"}, "other").status_code == 422
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(Audit).where(Audit.action == "task.accepted")))) == 1


def test_negotiation_then_decline_does_not_affect_other_invitation(harness):
    _app, ids, login = harness
    owner, recipient = login("lin"), login("qiao")
    discussion = topic(owner)
    first, second = invite(owner, discussion["id"], ids["qiao"]), invite(owner, discussion["id"], ids["qiao"])
    response = mutation(recipient, f"/invitations/{first['id']}/response", {"object_version": 1, "response": "negotiating", "note": "需要工具"}, "negotiate")
    assert response.json()["status"] == "negotiating"
    response = mutation(recipient, f"/invitations/{first['id']}/response", {"object_version": 2, "response": "declined"}, "decline")
    assert response.json()["status"] == "declined"
    all_items = recipient.get("/api/v1/invitations").json()
    assert next(item for item in all_items if item["id"] == second["id"])["status"] == "pending"


def test_freeze_invalidates_every_existing_session_and_idempotent_replay(harness):
    _app, ids, login = harness
    admin, recipient, another_session = login("admin"), login("qiao"), login("qiao")
    item = original(recipient)
    path = f"/utterances/{item['id']}/confirmations"
    assert mutation(recipient, path, {"object_version": 1}, "confirm").status_code == 200
    assert admin.post(f"/api/v1/admin/members/{ids['qiao']}/freeze").status_code == 200
    assert recipient.get("/api/v1/dashboard").status_code == 401
    assert another_session.get("/api/v1/auth/me").status_code == 401
    assert mutation(recipient, path, {"object_version": 1}, "confirm").status_code == 401


def test_registration_invitation_single_use_expired_and_password_hashed(harness):
    app, _ids, login = harness
    admin, public = login("admin"), TestClient(app)
    invitation = admin.post("/api/v1/admin/invites", json={"username": "new_member", "display_name": "合成新成员", "role": "member"}).json()
    registered = public.post("/api/v1/auth/register", json={"token": invitation["token"], "password": "new-demo-password-12"})
    assert registered.status_code == 200 and registered.json()["user"]["role"] == "member"
    assert public.post("/api/v1/auth/register", json={"token": invitation["token"], "password": "new-demo-password-12"}).status_code == 422
    expired = admin.post("/api/v1/admin/invites", json={"username": "expired_member", "display_name": "过期演示", "role": "member"}).json()
    with app.state.session_factory() as db:
        row = db.scalar(select(RegistrationInvite).where(RegistrationInvite.token_hash == digest(expired["token"])))
        row.expires_at = stamp(utcnow() - timedelta(days=1))
        db.commit()
    assert public.post("/api/v1/auth/register", json={"token": expired["token"], "password": "new-demo-password-12"}).status_code == 422


def test_session_idle_expiry_and_logout(harness):
    app, ids, login = harness
    client = login("qiao")
    with app.state.session_factory() as db:
        session = db.scalar(select(Session).where(Session.user_id == ids["qiao"]))
        session.last_seen_at = stamp(utcnow() - timedelta(minutes=6))
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    client = login("qiao")
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert "symsoil_session" not in client.cookies
    assert client.get("/api/v1/utterances").status_code == 401


def test_stance_replay_cannot_resurrect_withdrawn_shared_viewpoint(harness):
    _app, _ids, login = harness
    author, observer = login("qiao"), login("lin")
    item, discussion = original(author), topic(author)
    mutation(author, f"/utterances/{item['id']}/confirmations", {"object_version": 1}, "confirm")
    mutation(author, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": discussion["id"]}, "share")
    option = observer.get(f"/api/v1/topics/{discussion['id']}").json()["options"][0]
    path, body = f"/topics/{discussion['id']}/stances", {"option_id": option["id"], "option_version": 1, "stance": "reservation"}
    assert mutation(observer, path, body, "stance").json()["viewpoints"]
    author.post(f"/api/v1/utterances/{item['id']}/revoke", json={"object_version": 1})
    assert mutation(observer, path, body, "stance").json()["viewpoints"] == []


def test_concurrent_edits_cannot_overwrite_same_version(harness):
    _app, _ids, login = harness
    first, second = login("qiao"), login("qiao")
    item = original(first)
    def change(client, value):
        return client.patch(f"/api/v1/utterances/{item['id']}", json={"title": value, "text": value, "object_version": 1}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda pair: change(*pair), ((first, "one"), (second, "two"))))
    assert sorted(responses) == [200, 409]
    assert first.get("/api/v1/utterances").json()[0]["version"] == 2


def test_spa_fallback_never_captures_api_or_missing_asset(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>local synthetic app</title>")
    app = create_app(f"sqlite:///{tmp_path / 'spa.db'}", str(dist))
    client = TestClient(app)
    assert client.get("/topics/synthetic").status_code == 200
    assert client.get("/api/v1/not-real").status_code == 404
    assert client.get("/api/v1/not-real").headers["content-type"].startswith("application/json")
    assert client.get("/assets/missing.js").status_code == 404
    health = client.get("/api/v1/health").json()
    assert health == {"status": "ok", "stage": "R0", "ai_available": False}
