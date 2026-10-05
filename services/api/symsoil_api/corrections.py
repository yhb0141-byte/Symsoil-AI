"""Explicit bilateral correction sharing, independent from document publication."""
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_, select

from . import schemas as s
from .knowledge import current_publication
from .models import KnowledgeCorrection, KnowledgeDocument, User
from .security import stamp


def register_corrections(app, prefix, context, finish, audit, begin_idempotency, cas):
    def visible(db, actor, item_id):
        item = db.get(KnowledgeCorrection, item_id)
        if not item or actor.id not in (item.requester_id, item.recipient_id) or (actor.id == item.recipient_id and item.status == "withdrawn"):
            raise HTTPException(404, "记录不可访问")
        return item

    def detail(db, actor, item):
        data = {key: getattr(item, key) for key in ("id", "document_id", "revision_id", "document_version", "source_access_epoch", "requester_id", "recipient_id", "text", "response", "status", "version", "created_at", "updated_at", "responded_at", "withdrawn_at")}
        data["requester_name"] = db.get(User, item.requester_id).display_name
        data["recipient_name"] = db.get(User, item.recipient_id).display_name
        control = db.get(KnowledgeDocument, item.document_id)
        current = current_publication(db, control, actor)
        data["source"] = {"document_id": item.document_id, "revision_id": item.revision_id, "document_version": current[0].number, "access_epoch": control.access_epoch, "title": current[0].title} if current and current[0].id == item.revision_id else None
        return data

    def source_context(db, actor, document_id, revision_id, epoch):
        control = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id).with_for_update())
        current = current_publication(db, control, actor)
        if not current or current[0].id != revision_id:
            raise HTTPException(404, "关联版本当前不可查阅")
        if control.access_epoch != epoch:
            raise HTTPException(409, "资料授权已变化，请重新核对预览")
        recipient = db.get(User, control.owner_id)
        if recipient.id == actor.id:
            raise HTTPException(422, "这是本人资料，请在资料管理中另存新版本")
        if not recipient.active:
            raise HTTPException(422, "资料录入者当前无法接收，请转人工核实")
        return {"document_id": control.id, "revision_id": current[0].id, "document_version": current[0].number, "access_epoch": control.access_epoch, "title": current[0].title, "maintainer": current[0].maintainer, "recipient": {"id": recipient.id, "display_name": recipient.display_name}}

    def complete(db, actor, record, item):
        # Cache only identity; current source access and withdrawal are rebuilt.
        record.result = {"id": item.id}
        return finish(db, detail(db, actor, item))

    @app.get(prefix + "/documents/{document_id}/correction-context")
    def preview(document_id: str, revision_id: str = Query(min_length=1, max_length=36), access_epoch: int = Query(ge=1), ctx=Depends(context)):
        db, actor = ctx
        return finish(db, source_context(db, actor, document_id, revision_id, access_epoch))

    @app.post(prefix + "/knowledge-corrections")
    def create(body: s.CorrectionCreate, request: Request, ctx=Depends(context)):
        db, actor = ctx
        record, replay = begin_idempotency(db, actor, request, body)
        if replay:
            item = visible(db, actor, replay["id"])
            return finish(db, detail(db, actor, item))
        source = source_context(db, actor, body.document_id, body.revision_id, body.access_epoch)
        if body.expected_recipient_id != source["recipient"]["id"]:
            raise HTTPException(409, "接收人不匹配，请重新核对预览")
        now = stamp()
        item = KnowledgeCorrection(document_id=body.document_id, revision_id=body.revision_id, document_version=source["document_version"], source_access_epoch=body.access_epoch, requester_id=actor.id, recipient_id=source["recipient"]["id"], text=body.text, created_at=now, updated_at=now)
        db.add(item)
        db.flush()
        audit(db, actor, "correction.create", "correction", item.id, item.version)
        return complete(db, actor, record, item)

    @app.get(prefix + "/knowledge-corrections")
    def listing(ctx=Depends(context)):
        db, actor = ctx
        items = list(db.scalars(select(KnowledgeCorrection).where(or_(KnowledgeCorrection.requester_id == actor.id, and_(KnowledgeCorrection.recipient_id == actor.id, KnowledgeCorrection.status != "withdrawn"))).order_by(KnowledgeCorrection.updated_at.desc(), KnowledgeCorrection.id)))
        return finish(db, {"items": [detail(db, actor, item) for item in items], "counts": {"sent": sum(item.requester_id == actor.id for item in items), "incoming": sum(item.recipient_id == actor.id for item in items), "pending_incoming": sum(item.recipient_id == actor.id and item.status == "submitted" for item in items)}})

    @app.get(prefix + "/knowledge-corrections/{item_id}")
    def read(item_id: str, ctx=Depends(context)):
        db, actor = ctx
        return finish(db, detail(db, actor, visible(db, actor, item_id)))

    @app.post(prefix + "/knowledge-corrections/{item_id}/respond")
    def respond(item_id: str, body: s.CorrectionRespond, request: Request, ctx=Depends(context)):
        db, actor = ctx
        item = visible(db, actor, item_id)
        if actor.id != item.recipient_id:
            raise HTTPException(404, "记录不可访问")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay:
            return finish(db, detail(db, actor, item))
        if item.status != "submitted":
            raise HTTPException(409, "此请求已经回应或撤回")
        if not db.get(User, item.requester_id).active:
            raise HTTPException(409, "请求者当前无法接收，请保留人工处理路径")
        now = stamp()
        cas(db, KnowledgeCorrection, item, body.object_version, {"response": body.text, "status": "responded", "version": body.object_version + 1, "responded_at": now, "updated_at": now}, KnowledgeCorrection.status == "submitted")
        audit(db, actor, "correction.respond", "correction", item.id, item.version)
        return complete(db, actor, record, item)

    @app.post(prefix + "/knowledge-corrections/{item_id}/withdraw")
    def withdraw(item_id: str, body: s.Version, request: Request, ctx=Depends(context)):
        db, actor = ctx
        item = visible(db, actor, item_id)
        if actor.id != item.requester_id:
            raise HTTPException(404, "记录不可访问")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay:
            return finish(db, detail(db, actor, item))
        if item.status == "withdrawn":
            raise HTTPException(409, "此请求已经撤回")
        now = stamp()
        cas(db, KnowledgeCorrection, item, body.object_version, {"status": "withdrawn", "version": body.object_version + 1, "withdrawn_at": now, "updated_at": now}, KnowledgeCorrection.status != "withdrawn")
        audit(db, actor, "correction.withdraw", "correction", item.id, item.version)
        return complete(db, actor, record, item)
