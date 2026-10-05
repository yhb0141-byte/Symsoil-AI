from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from . import schemas as s
from .models import ApprovalAuthority, Decision, DecisionApproval, DecisionCondition, Invitation, Option, Participant, Topic, User
from .security import stamp


def register_decisions(app, prefix, context, finish, audit, begin_idempotency, complete_idempotency, cas):
    dependency = Depends(context)
    def topic_for(db, actor, topic_id, owner=False):
        topic = db.get(Topic, topic_id)
        if not topic or not db.get(Participant, (topic_id, actor.id)) or (owner and topic.owner_id != actor.id):
            raise HTTPException(404, "记录不可访问")
        return topic

    def authority_for(db, member_id, topic_id):
        return db.scalar(select(ApprovalAuthority).where(ApprovalAuthority.member_id == member_id, ApprovalAuthority.topic_id == topic_id, ApprovalAuthority.active.is_(True)))

    def authority_data(db, item):
        return {"id": item.id, "member_id": item.member_id, "member_name": db.get(User, item.member_id).display_name, "topic_id": item.topic_id, "active": item.active, "version": item.version, "basis": item.basis, "created_at": item.created_at, "revoked_at": item.revoked_at}

    def decision_for(db, actor, item_id, owner=False):
        item = db.get(Decision, item_id)
        if not item:
            raise HTTPException(404, "记录不可访问")
        topic_for(db, actor, item.topic_id, owner=owner)
        return item

    def detail(db, item):
        conditions = list(db.scalars(select(DecisionCondition).where(DecisionCondition.decision_id == item.id).order_by(DecisionCondition.kind, DecisionCondition.id)))
        approvals = list(db.scalars(select(DecisionApproval).where(DecisionApproval.decision_id == item.id, DecisionApproval.decision_version == item.version).order_by(DecisionApproval.approver_id)))
        return {
            **{key: getattr(item, key) for key in ("id", "topic_id", "option_id", "option_version", "author_id", "title", "text", "status", "version", "rule_version", "required_approver_ids", "required_invitation_ids", "created_at", "updated_at", "effective_at", "started_at")},
            "conditions": [{key: getattr(value, key) for key in ("id", "kind", "label", "satisfied", "version", "verifier_id", "verified_at")} for value in conditions],
            "approvals": [{"approver_id": value.approver_id, "approver_name": db.get(User, value.approver_id).display_name, "decision_version": value.decision_version, "authority_id": value.authority_id, "authority_version": value.authority_version, "created_at": value.created_at} for value in approvals],
            "synthetic": True,
        }

    def maybe_effective(db, item):
        if item.status != "pending":
            return
        if db.scalar(select(DecisionCondition.id).where(DecisionCondition.decision_id == item.id, DecisionCondition.kind == "effect", DecisionCondition.satisfied.is_(False)).limit(1)):
            return
        approvals = {value.approver_id: value for value in db.scalars(select(DecisionApproval).where(DecisionApproval.decision_id == item.id, DecisionApproval.decision_version == item.version))}
        for member_id in item.required_approver_ids:
            authority, approval = authority_for(db, member_id, item.topic_id), approvals.get(member_id)
            user = db.get(User, member_id)
            if not user or not user.active or not authority or (approval and (approval.authority_id != authority.id or approval.authority_version != authority.version)):
                item.status, item.version, item.updated_at = "blocked", item.version + 1, stamp()
                db.execute(delete(DecisionApproval).where(DecisionApproval.decision_id == item.id))
                return
            if not approval:
                return
        item.status, item.effective_at, item.updated_at = "effective", stamp(), stamp()

    @app.post(prefix + "/admin/approval-authorities")
    def grant_authority(body: s.ApprovalAuthorityCreate, request: Request, ctx=dependency):
        db, actor = ctx
        if actor.role != "admin":
            raise HTTPException(403, "需要账号管理权限")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, replay)
        member, topic = db.get(User, body.member_id), db.get(Topic, body.topic_id)
        if not member or not member.active or not topic or not db.get(Participant, (topic.id, member.id)):
            raise HTTPException(404, "记录不可访问")
        item = db.scalar(select(ApprovalAuthority).where(ApprovalAuthority.member_id == member.id, ApprovalAuthority.topic_id == topic.id))
        if item and item.active:
            raise HTTPException(409, "该议题批准资格已经有效")
        if item:
            item.active, item.version, item.basis, item.revoked_at = True, item.version + 1, body.basis, None
        else:
            item = ApprovalAuthority(member_id=member.id, topic_id=topic.id, basis=body.basis, created_at=stamp())
            db.add(item)
        db.flush()
        audit(db, actor, "approval.authority.grant", "approval_authority", item.id, item.version)
        return complete_idempotency(db, record, authority_data(db, item))

    @app.post(prefix + "/admin/approval-authorities/{authority_id}/revoke")
    def revoke_authority(authority_id: str, body: s.Version, request: Request, ctx=dependency):
        db, actor = ctx
        if actor.role != "admin":
            raise HTTPException(403, "需要账号管理权限")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, replay)
        item = db.get(ApprovalAuthority, authority_id)
        if not item or not item.active:
            raise HTTPException(404, "记录不可访问")
        cas(db, ApprovalAuthority, item, body.object_version, {"active": False, "version": body.object_version + 1, "revoked_at": stamp()})
        blocked = []
        for decision in db.scalars(select(Decision).where(Decision.topic_id == item.topic_id, Decision.status == "pending")):
            if item.member_id in decision.required_approver_ids:
                decision.status, decision.version, decision.updated_at = "blocked", decision.version + 1, stamp()
                db.execute(delete(DecisionApproval).where(DecisionApproval.decision_id == decision.id))
                blocked.append(decision.id)
        db.info["authority_blocked_decisions"] = blocked
        audit(db, actor, "approval.authority.revoke", "approval_authority", item.id, item.version)
        return complete_idempotency(db, record, {**authority_data(db, item), "blocked_decision_ids": blocked})

    @app.post(prefix + "/topics/{topic_id}/decisions")
    def create_decision(topic_id: str, body: s.DecisionCreate, ctx=dependency):
        db, actor = ctx
        topic_for(db, actor, topic_id, owner=True)
        option = db.get(Option, body.option_id)
        if not option or option.topic_id != topic_id or option.version != body.option_version:
            raise HTTPException(409, "方案版本已经变化或不可访问")
        now = stamp()
        item = Decision(topic_id=topic_id, option_id=option.id, option_version=option.version, author_id=actor.id, title=body.title, text=body.text, created_at=now, updated_at=now)
        db.add(item)
        db.flush()
        db.add_all([DecisionCondition(decision_id=item.id, kind=kind, label=label) for kind, values in (("effect", body.effect_conditions), ("resource", body.resource_conditions)) for label in values])
        db.flush()
        audit(db, actor, "decision.create", "decision", item.id, item.version)
        return finish(db, detail(db, item))

    @app.get(prefix + "/topics/{topic_id}/decisions")
    def list_decisions(topic_id: str, ctx=dependency):
        db, actor = ctx
        topic_for(db, actor, topic_id)
        return finish(db, [detail(db, item) for item in db.scalars(select(Decision).where(Decision.topic_id == topic_id).order_by(Decision.created_at))])

    @app.post(prefix + "/decisions/{item_id}/submit")
    def submit_decision(item_id: str, body: s.DecisionSubmit, request: Request, ctx=dependency):
        db, actor = ctx
        item = decision_for(db, actor, item_id, owner=True)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, detail(db, item))
        if item.status not in ("draft", "blocked"):
            raise HTTPException(422, "当前决定不能进入待批准")
        if item.rule_version == body.rule_version:
            raise HTTPException(422, "阻断后必须使用新的规则版本")
        for member_id in body.required_approver_ids:
            member = db.get(User, member_id)
            if not member or not member.active or not authority_for(db, member_id, item.topic_id):
                raise HTTPException(422, "必需批准者缺少当前议题资格")
        for invitation_id in body.required_invitation_ids:
            invitation = db.get(Invitation, invitation_id)
            if not invitation or invitation.topic_id != item.topic_id:
                raise HTTPException(422, "必需任务不属于当前议题")
        cas(db, Decision, item, body.object_version, {"status": "pending", "version": body.object_version + 1, "rule_version": body.rule_version, "required_approver_ids": list(body.required_approver_ids), "required_invitation_ids": list(body.required_invitation_ids), "updated_at": stamp()})
        db.execute(delete(DecisionApproval).where(DecisionApproval.decision_id == item.id))
        audit(db, actor, "decision.submit", "decision", item.id, item.version)
        return complete_idempotency(db, record, detail(db, item))

    @app.post(prefix + "/decisions/{item_id}/conditions/{condition_id}/verify")
    def verify_condition(item_id: str, condition_id: str, body: s.DecisionConditionVerify, request: Request, ctx=dependency):
        db, actor = ctx
        item = decision_for(db, actor, item_id, owner=True)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, detail(db, item))
        condition = db.get(DecisionCondition, condition_id)
        if not condition or condition.decision_id != item.id or item.status in ("started",) or (condition.kind == "effect" and item.status == "effective"):
            raise HTTPException(404, "记录不可访问")
        cas(db, DecisionCondition, condition, body.condition_version, {"satisfied": body.satisfied, "version": body.condition_version + 1, "verifier_id": actor.id if body.satisfied else None, "verified_at": stamp() if body.satisfied else None})
        maybe_effective(db, item)
        audit(db, actor, "decision.condition.verify", "decision_condition", condition.id, condition.version)
        return complete_idempotency(db, record, detail(db, item))

    @app.post(prefix + "/decisions/{item_id}/approvals")
    def approve(item_id: str, body: s.DecisionApprove, request: Request, ctx=dependency):
        db, actor = ctx
        item = decision_for(db, actor, item_id)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, detail(db, item))
        if item.status != "pending" or item.version != body.object_version or actor.id not in item.required_approver_ids:
            raise HTTPException(403, "本人不是此决定版本的当前必需批准者")
        authority = authority_for(db, actor.id, item.topic_id)
        if not authority:
            raise HTTPException(403, "本人当前没有此议题批准资格")
        db.add(DecisionApproval(decision_id=item.id, decision_version=item.version, approver_id=actor.id, authority_id=authority.id, authority_version=authority.version, created_at=stamp()))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "本人已经批准此决定版本")
        maybe_effective(db, item)
        audit(db, actor, "decision.approve", "decision", item.id, item.version)
        return complete_idempotency(db, record, detail(db, item))

    @app.post(prefix + "/decisions/{item_id}/start")
    def start(item_id: str, body: s.DecisionStart, request: Request, ctx=dependency):
        db, actor = ctx
        item = decision_for(db, actor, item_id, owner=True)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, detail(db, item))
        if item.status != "effective" or item.version != body.object_version:
            raise HTTPException(422, "决定尚未生效或版本已变化")
        missing_tasks = [invitation_id for invitation_id in item.required_invitation_ids if not (invitation := db.get(Invitation, invitation_id)) or invitation.status != "accepted"]
        missing_resources = list(db.scalars(select(DecisionCondition.label).where(DecisionCondition.decision_id == item.id, DecisionCondition.kind == "resource", DecisionCondition.satisfied.is_(False))))
        if missing_tasks or missing_resources:
            raise HTTPException(422, {"message": "行动开始条件尚未齐备", "missing_task_ids": missing_tasks, "missing_resources": missing_resources})
        cas(db, Decision, item, body.object_version, {"status": "started", "version": body.object_version + 1, "started_at": stamp(), "updated_at": stamp()})
        audit(db, actor, "decision.start", "decision", item.id, item.version)
        return complete_idempotency(db, record, detail(db, item))
