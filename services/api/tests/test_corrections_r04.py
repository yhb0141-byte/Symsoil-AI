"""Privacy, lifecycle, and independent publication boundaries of corrections."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select

from symsoil_api.models import Audit, KnowledgeCorrection, KnowledgeDocument, KnowledgeRevision, User
from symsoil_api.security import utcnow
from test_knowledge_r03 import fields, post

P = "/api/v1"


def setup(harness):
    app, ids, login = harness
    owner, sender, outsider = login("qiao"), login("lin"), login("admin")
    doc = sender.get(P + "/documents").json()[0]
    data = {"document_id": doc["id"], "revision_id": doc["revision_id"], "access_epoch": doc["access_epoch"], "expected_recipient_id": ids["qiao"], "text": "PRIVATE_CORRECTION：这段工具条件是否仍适用？", "consent": True}
    return app, ids, owner, sender, outsider, doc, data


def create(sender, data, key=None):
    result = post(sender, "/knowledge-corrections", data, key)
    assert result.status_code == 200, result.text
    return result.json()


def route(item, action=""):
    return f"/knowledge-corrections/{item['id']}" + (f"/{action}" if action else "")


def test_preview_is_read_only_and_names_actual_owner(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    preview = sender.get(P + f"/documents/{doc['id']}/correction-context", params={"revision_id": doc["revision_id"], "access_epoch": doc["access_epoch"]})
    assert preview.status_code == 200
    assert preview.json()["recipient"] == {"id": ids["qiao"], "display_name": "乔雨 · 合成成员"}
    assert "body" not in preview.json()
    assert sender.get(P + "/knowledge-corrections").json()["items"] == []
    assert post(owner, "/knowledge-corrections", data).status_code == 422
    assert post(sender, "/knowledge-corrections", {**data, "expected_recipient_id": ids["admin"]}).status_code == 409
    with app.state.session_factory() as db:
        assert db.scalars(select(KnowledgeCorrection)).all() == []


def test_request_and_response_private_and_do_not_change_publication(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    publication = owner.get(P + f"/knowledge/{doc['id']}").json()
    topics = sender.get(P + "/topics").json()
    invitations = owner.get(P + "/invitations").json()
    item = create(sender, data)
    assert item["status"] == "submitted" and item["response"] is None
    assert sender.get(P + "/knowledge-corrections").json()["counts"] == {"sent": 1, "incoming": 0, "pending_incoming": 0}
    assert owner.get(P + "/knowledge-corrections").json()["counts"] == {"sent": 0, "incoming": 1, "pending_incoming": 1}
    assert outsider.get(P + "/knowledge-corrections").json() == {"items": [], "counts": {"sent": 0, "incoming": 0, "pending_incoming": 0}}
    assert outsider.get(P + route(item)).status_code == 404
    for client in [sender, outsider]:
        assert post(client, route(item, "respond"), {"object_version": 1, "text": "冒充回应", "consent": True}).status_code == 404
    response = post(owner, route(item, "respond"), {"object_version": 1, "text": "PRIVATE_REPLY：会另存新版本核对，并非已经发布。", "consent": True})
    assert response.status_code == 200 and response.json()["status"] == "responded"
    assert "PRIVATE_REPLY" in sender.get(P + route(item)).json()["response"]
    assert owner.get(P + "/knowledge-corrections").json()["counts"]["pending_incoming"] == 0
    assert owner.get(P + f"/knowledge/{doc['id']}").json() == publication
    assert sender.get(P + "/topics").json() == topics
    assert owner.get(P + "/invitations").json() == invitations
    assert "PRIVATE_CORRECTION" not in sender.get(P + "/documents").text
    assert post(sender, "/knowledge/answers", {"question": "PRIVATE_CORRECTION", "use_model": False}).json()["mode"] == "insufficient"
    with app.state.session_factory() as db:
        assert all("PRIVATE_" not in str(event.__dict__) for event in db.scalars(select(Audit)))


@pytest.mark.parametrize("changes", [
    {"consent": False}, {"consent": 1}, {"consent": "true"},
    {"text": " "}, {"text": "a\x00b"}, {"text": "\ud800"}, {"text": "a" * 2001},
    {"requester_id": "spoof"}, {"recipient_id": "spoof"}, {"status": "responded"}, {"response": "fake"},
])
def test_strict_consent_plain_text_and_no_identity_or_status_override(harness, changes):
    *_, sender, outsider, doc, data = setup(harness)
    result = post(sender, "/knowledge-corrections", {**data, **changes})
    assert result.status_code == 422
    assert "PRIVATE_CORRECTION" not in result.text
    assert sender.get(P + "/knowledge-corrections").json()["items"] == []


def test_old_epoch_is_rejected_even_when_requester_still_has_access(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    control = owner.get(P + f"/knowledge/{doc['id']}").json()
    assert post(owner, f"/knowledge/{doc['id']}/restrict", {"object_version": control["version"], "scope": "members", "member_ids": [ids["lin"]]}).status_code == 200
    assert sender.get(P + f"/documents/{doc['id']}").status_code == 200
    assert post(sender, "/knowledge-corrections", data).status_code == 409
    fresh = sender.get(P + f"/documents/{doc['id']}").json()
    assert create(sender, {**data, "access_epoch": fresh["access_epoch"]})["source_access_epoch"] == fresh["access_epoch"]


@pytest.mark.parametrize("change", ["withdraw", "restrict", "expiry", "replace"])
def test_source_becoming_unavailable_never_resurrects_source_snapshot(harness, change):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    key = str(uuid4())
    item = create(sender, data, key)
    control = owner.get(P + f"/knowledge/{doc['id']}").json()
    if change == "withdraw":
        assert post(owner, f"/knowledge/{doc['id']}/withdraw", {"object_version": control["version"]}).status_code == 200
    elif change == "restrict":
        assert post(owner, f"/knowledge/{doc['id']}/restrict", {"object_version": control["version"], "scope": "members", "member_ids": []}).status_code == 200
    elif change == "expiry":
        with app.state.session_factory() as db:
            db.get(KnowledgeRevision, doc["revision_id"]).effective_until = (utcnow() - timedelta(seconds=1)).isoformat()
            db.commit()
    else:
        new = owner.patch(P + f"/knowledge/{doc['id']}", json={"object_version": control["version"], **fields(title="NEW_VERSION_PRIVATE_TITLE")}).json()
        submitted = post(owner, f"/knowledge/{doc['id']}/submit", {"object_version": new["version"], "revision_id": new["latest"]["id"], "reviewer_id": ids["lin"], "consent": True}).json()
        assert post(sender, f"/knowledge/{doc['id']}/review", {"object_version": submitted["version"], "revision_id": new["latest"]["id"], "decision": "approve", "reason": "合成改版"}).status_code == 200
    for result in [sender.get(P + route(item)), post(sender, "/knowledge-corrections", data, key)]:
        assert result.status_code == 200
        assert result.json()["source"] is None
        assert doc["title"] not in result.text and "NEW_VERSION_PRIVATE_TITLE" not in result.text
        assert result.json()["text"] == data["text"]
        assert result.json()["revision_id"] == doc["revision_id"]
    assert post(sender, "/knowledge-corrections", data).status_code == 404
    assert post(owner, route(item, "respond"), {"object_version": 1, "text": "原资料已停止提供，本回应单独分享。", "consent": True}).status_code == 200


@pytest.mark.parametrize("respond_first", [False, True])
def test_withdraw_revokes_recipient_and_all_old_replays(harness, respond_first):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    create_key, response_key, withdraw_key = str(uuid4()), str(uuid4()), str(uuid4())
    item = create(sender, data, create_key)
    reply = {"object_version": 1, "text": "PRIVATE_REPLY", "consent": True}
    if respond_first:
        item = post(owner, route(item, "respond"), reply, response_key).json()
    withdrawal = {"object_version": item["version"]}
    assert post(owner, route(item, "withdraw"), withdrawal).status_code == 404
    withdrawn = post(sender, route(item, "withdraw"), withdrawal, withdraw_key).json()
    assert withdrawn["status"] == "withdrawn"
    assert owner.get(P + route(item)).status_code == 404
    assert post(owner, route(item, "respond"), reply, response_key).status_code == 404
    assert owner.get(P + "/knowledge-corrections").json()["items"] == []
    assert owner.get(P + "/knowledge-corrections").json()["counts"]["incoming"] == 0
    for result in [post(sender, "/knowledge-corrections", data, create_key), post(sender, route(item, "withdraw"), withdrawal, withdraw_key)]:
        assert result.json()["status"] == "withdrawn"
    assert sender.get(P + route(item)).json()["text"] == data["text"]


def test_duplicate_different_body_and_second_response_cannot_overwrite(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    key = str(uuid4())
    item = create(sender, data, key)
    assert create(sender, data, key)["id"] == item["id"]
    assert post(sender, "/knowledge-corrections", {**data, "text": "changed"}, key).status_code == 409
    reply = {"object_version": 1, "text": "合成回应", "consent": True}
    rkey = str(uuid4())
    assert post(owner, route(item, "respond"), reply, rkey).status_code == 200
    assert post(owner, route(item, "respond"), reply, rkey).json()["version"] == 2
    assert post(owner, route(item, "respond"), {**reply, "object_version": 2}).status_code == 409


def test_freeze_does_not_automatically_revoke_shared_history(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    item = create(sender, data)
    with app.state.session_factory() as db:
        db.get(User, ids["lin"]).active = False
        db.commit()
    assert sender.get(P + route(item)).status_code == 401
    assert owner.get(P + route(item)).status_code == 200
    assert post(owner, route(item, "respond"), {"object_version": 1, "text": "不能发送给冻结账号", "consent": True}).status_code == 409


def test_inactive_recipient_blocks_new_request(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    item = create(sender, data)
    with app.state.session_factory() as db:
        db.get(User, ids["qiao"]).active = False
        db.commit()
    assert post(sender, "/knowledge-corrections", data).status_code == 422
    assert sender.get(P + route(item)).status_code == 200
    assert owner.get(P + route(item)).status_code == 401


def test_response_and_withdraw_are_serialized_and_never_revive(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    item = create(sender, data)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replying = pool.submit(post, owner, route(item, "respond"), {"object_version": 1, "text": "竞争中的回应", "consent": True})
        withdrawing = pool.submit(post, sender, route(item, "withdraw"), {"object_version": 1})
        codes = [replying.result().status_code, withdrawing.result().status_code]
    assert codes.count(200) == 1 and all(code in (200, 404, 409) for code in codes)
    current = sender.get(P + route(item)).json()
    assert current["version"] == 2
    if current["status"] != "withdrawn":
        assert post(sender, route(item, "withdraw"), {"object_version": 2}).status_code == 200
    assert owner.get(P + route(item)).status_code == 404


def test_new_table_does_not_store_source_snapshots(harness):
    app, ids, owner, sender, outsider, doc, data = setup(harness)
    item = create(sender, data)
    columns = {column["name"] for column in inspect(app.state.engine).get_columns("knowledge_corrections")}
    assert not columns.intersection({"title", "body", "source", "quote", "maintainer"})
    with app.state.session_factory() as db:
        row = db.get(KnowledgeCorrection, item["id"])
        assert row.document_version == doc["version"] and row.revision_id == doc["revision_id"]
