from uuid import uuid4


P = "/api/v1"


def post(client, path, data, key=None):
    return client.post(P + path, json=data, headers={"Idempotency-Key": key or str(uuid4())})


def setup(harness):
    _app, ids, login = harness
    admin, owner, member = login("admin"), login("lin"), login("qiao")
    topic = owner.get(P + "/topics").json()[0]
    option = owner.get(P + f"/topics/{topic['id']}").json()["options"][0]
    invitation = owner.get(P + f"/topics/{topic['id']}").json()["invitations"][0]
    return ids, admin, owner, member, topic, option, invitation


def grant(admin, member_id, topic_id, basis="合成规则登记；不代表现实授权"):
    response = post(admin, "/admin/approval-authorities", {"member_id": member_id, "topic_id": topic_id, "basis": basis})
    assert response.status_code == 200, response.text
    return response.json()


def create(owner, topic, option, effect=None, resource=None):
    response = owner.post(P + f"/topics/{topic['id']}/decisions", json={"option_id": option["id"], "option_version": option["version"], "title": "合成试办决定", "text": "仅验证批准与开始条件，不构成真实场地许可。", "effect_conditions": effect or [], "resource_conditions": resource or []})
    assert response.status_code == 200, response.text
    return response.json()


def test_two_person_approval_is_distinct_from_stance_and_task_acceptance(harness):
    ids, admin, owner, member, topic, option, invitation = setup(harness)
    grant(admin, ids["admin"], topic["id"])
    grant(admin, ids["qiao"], topic["id"])
    decision = create(owner, topic, option, ["场地负责人已核对试办边界"], ["清理工具已经到位"])
    submitted = post(owner, f"/decisions/{decision['id']}/submit", {"object_version": 1, "rule_version": "synthetic-rule-v1", "required_approver_ids": [ids["admin"], ids["qiao"]], "required_invitation_ids": [invitation["id"]]}).json()
    assert submitted["status"] == "pending" and submitted["approvals"] == []

    # A discussion stance remains only a stance and cannot create approval.
    current_topic = owner.get(P + f"/topics/{topic['id']}").json()
    stance = post(member, f"/topics/{topic['id']}/stances", {"option_id": option["id"], "option_version": option["version"], "stance": "support", "condition": ""})
    assert stance.status_code == 200
    assert owner.get(P + f"/topics/{topic['id']}/decisions").json()[0]["approvals"] == []

    first = post(member, f"/decisions/{decision['id']}/approvals", {"object_version": 2, "consent": True}, "member-approval").json()
    assert first["status"] == "pending" and len(first["approvals"]) == 1
    effect = next(item for item in first["conditions"] if item["kind"] == "effect")
    verified = post(owner, f"/decisions/{decision['id']}/conditions/{effect['id']}/verify", {"object_version": 2, "condition_version": 1, "satisfied": True}).json()
    assert verified["status"] == "pending"
    effective = post(admin, f"/decisions/{decision['id']}/approvals", {"object_version": 2, "consent": True}).json()
    assert effective["status"] == "effective" and effective["effective_at"]
    assert post(member, f"/decisions/{decision['id']}/approvals", {"object_version": 2, "consent": True}, "member-approval").json()["status"] == "effective"

    blocked = post(owner, f"/decisions/{decision['id']}/start", {"object_version": 2, "confirm_start": True})
    assert blocked.status_code == 422
    accepted = post(member, f"/invitations/{invitation['id']}/response", {"object_version": invitation["version"], "response": "accepted", "note": "本人仅接受这项合成任务"})
    assert accepted.status_code == 200
    resource = next(item for item in effective["conditions"] if item["kind"] == "resource")
    assert post(owner, f"/decisions/{decision['id']}/conditions/{resource['id']}/verify", {"object_version": 2, "condition_version": 1, "satisfied": True}).status_code == 200
    started = post(owner, f"/decisions/{decision['id']}/start", {"object_version": 2, "confirm_start": True}).json()
    assert started["status"] == "started" and started["started_at"]


def test_authority_revocation_blocks_and_requires_new_rule_and_all_new_approvals(harness):
    ids, admin, owner, member, topic, option, _invitation = setup(harness)
    admin_authority = grant(admin, ids["admin"], topic["id"])
    member_authority = grant(admin, ids["qiao"], topic["id"])
    grant(admin, ids["lin"], topic["id"])
    decision = create(owner, topic, option)
    pending = post(owner, f"/decisions/{decision['id']}/submit", {"object_version": 1, "rule_version": "synthetic-rule-v1", "required_approver_ids": [ids["qiao"], ids["admin"]], "required_invitation_ids": []}).json()
    assert post(member, f"/decisions/{decision['id']}/approvals", {"object_version": pending["version"], "consent": True}).status_code == 200

    revoked = post(admin, f"/admin/approval-authorities/{member_authority['id']}/revoke", {"object_version": member_authority["version"]}).json()
    assert decision["id"] in revoked["blocked_decision_ids"]
    blocked = owner.get(P + f"/topics/{topic['id']}/decisions").json()[0]
    assert blocked["status"] == "blocked" and blocked["approvals"] == [] and blocked["version"] == 3
    assert post(admin, f"/decisions/{decision['id']}/approvals", {"object_version": 2, "consent": True}).status_code == 403
    same_rule = post(owner, f"/decisions/{decision['id']}/submit", {"object_version": 3, "rule_version": "synthetic-rule-v1", "required_approver_ids": [ids["lin"], ids["admin"]], "required_invitation_ids": []})
    assert same_rule.status_code == 422
    restarted = post(owner, f"/decisions/{decision['id']}/submit", {"object_version": 3, "rule_version": "synthetic-rule-v2", "required_approver_ids": [ids["lin"], ids["admin"]], "required_invitation_ids": []}).json()
    assert restarted["status"] == "pending" and restarted["version"] == 4
    assert post(member, f"/decisions/{decision['id']}/approvals", {"object_version": 4, "consent": True}).status_code == 403
    assert post(owner, f"/decisions/{decision['id']}/approvals", {"object_version": 4, "consent": True}).json()["status"] == "pending"
    final = post(admin, f"/decisions/{decision['id']}/approvals", {"object_version": 4, "consent": True}).json()
    assert final["status"] == "effective"


def test_normal_member_cannot_register_authority_or_draft_decision(harness):
    ids, _admin, owner, member, topic, option, _invitation = setup(harness)
    assert post(member, "/admin/approval-authorities", {"member_id": ids["qiao"], "topic_id": topic["id"], "basis": "forged"}).status_code == 403
    response = member.post(P + f"/topics/{topic['id']}/decisions", json={"option_id": option["id"], "option_version": option["version"], "title": "伪造", "text": "伪造", "effect_conditions": [], "resource_conditions": []})
    assert response.status_code == 404


def test_account_freeze_before_final_approval_blocks_the_decision(harness):
    ids, admin, owner, member, topic, option, _invitation = setup(harness)
    grant(admin, ids["admin"], topic["id"])
    grant(admin, ids["qiao"], topic["id"])
    decision = create(owner, topic, option)
    pending = post(owner, f"/decisions/{decision['id']}/submit", {"object_version": 1, "rule_version": "synthetic-rule-v1", "required_approver_ids": [ids["qiao"], ids["admin"]], "required_invitation_ids": []}).json()
    assert post(member, f"/decisions/{decision['id']}/approvals", {"object_version": pending["version"], "consent": True}).status_code == 200
    assert admin.post(P + f"/admin/members/{ids['qiao']}/freeze").status_code == 200
    result = post(admin, f"/decisions/{decision['id']}/approvals", {"object_version": 2, "consent": True}).json()
    assert result["status"] == "blocked" and result["approvals"] == [] and result["version"] == 3
