"""Small text library: immutable revisions, explicit review, and one current ACL.

Only current authorized publications can enter the directory or a model request.
Private drafts never enter the legacy Document snapshot table.
"""

import re
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from pydantic import ValidationError

from . import schemas as s
from .models import Document, KnowledgeAudience, KnowledgeDocument, KnowledgeReview, KnowledgeRevision, User, uid
from .security import stamp, utcnow

REVISION_FIELDS = ("id", "document_id", "number", "title", "category", "body", "source", "rights", "purpose", "maintainer", "effective_until", "requested_scope", "requested_member_ids", "created_at")


def revision_data(item):
    return {key: getattr(item, key) for key in REVISION_FIELDS}


def revision_for(db, control, revision_id):
    item = db.get(KnowledgeRevision, revision_id) if revision_id else None
    return item if item and item.document_id == control.id else None


def unexpired(item):
    if not item.effective_until:
        return True
    try:
        when = datetime.fromisoformat(item.effective_until.replace("Z", "+00:00"))
        return when.tzinfo is not None and when.utcoffset() is not None and when > utcnow()
    except (ValueError, TypeError):
        return False


def current_publication(db, control, actor):
    if not control or control.withdrawn_at or not control.published_revision_id or not actor.active:
        return None
    revision = revision_for(db, control, control.published_revision_id)
    audience = db.get(KnowledgeAudience, control.id)
    if not revision or not unexpired(revision) or not audience or audience.revision_id != revision.id:
        return None
    snapshot = db.get(Document, control.id)
    if not snapshot or snapshot.version != revision.number or any(getattr(snapshot, key) != getattr(revision, key) for key in ("title", "category", "body", "source")):
        return None
    if audience.scope not in ("community", "members"):
        return None
    if audience.scope == "members" and actor.id != control.owner_id and actor.id not in audience.member_ids:
        return None
    return revision, audience


def visible_publications(db, actor, q=""):
    # The explicit metadata join quarantines every legacy row without approval
    # metadata. Literal LIKE metacharacters are escaped before matching.
    statement = select(KnowledgeDocument).join(Document, Document.id == KnowledgeDocument.id).order_by(Document.title, Document.id)
    if q.strip():
        term = q.strip()
        statement = statement.where(Document.title.contains(term, autoescape=True) | Document.body.contains(term, autoescape=True))
    return [(item, publication[0], publication[1]) for item in db.scalars(statement) if (publication := current_publication(db, item, actor))]


def snippets(revision, terms=()):
    lines = revision.body.splitlines() or [revision.body]
    scored = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        score = sum(term in line.casefold() for term in terms)
        scored.append((score, index, line))
    scored.sort(key=lambda value: (-value[0], value[1]))
    result = []
    for _score, index, line in scored[:3]:
        # A long line can be partially quoted; line coordinates identify the
        # source line, while the quote remains an exact original substring.
        position = next((line.casefold().find(term) for term in terms if term in line.casefold()), 0)
        start = max(0, position - 200)
        quote = line[start:start + 800]
        result.append({"citation_id": f"{revision.id}:L{index}:C{start}", "quote": quote, "start_line": index, "end_line": index})
    return result


def published_data(db, control, revision, audience, terms=()):
    owner = db.get(User, control.owner_id)
    return {"id": control.id, "title": revision.title, "category": revision.category, "body": revision.body, "version": revision.number, "source": revision.source, "updated_at": db.get(Document, control.id).updated_at, "revision_id": revision.id, "owner_name": owner.display_name, "maintainer": revision.maintainer, "purpose": revision.purpose, "effective_until": revision.effective_until, "scope": audience.scope, "access_epoch": control.access_epoch, "snippets": snippets(revision, terms)}


def knowledge_detail(db, control):
    owner = db.get(User, control.owner_id)
    audience = db.get(KnowledgeAudience, control.id)
    data = {key: getattr(control, key) for key in ("id", "version", "owner_id", "reviewer_id", "access_epoch", "withdrawn_at")}
    data["owner_name"] = owner.display_name
    for key, reference in (("latest", control.latest_revision_id), ("submitted", control.submitted_revision_id), ("published", control.published_revision_id)):
        revision = revision_for(db, control, reference)
        data[key] = revision_data(revision) if revision else None
    active = current_publication(db, control, owner) is not None
    data["publication_active"] = active
    data["audience"] = {"scope": audience.scope, "member_ids": list(audience.member_ids)} if active else None
    data["reviews"] = [{"id": item.id, "document_id": item.document_id, "revision_id": item.revision_id, "reviewer_id": item.reviewer_id, "reviewer_name": db.get(User, item.reviewer_id).display_name, "decision": item.decision, "reason": item.reason, "created_at": item.created_at} for item in db.scalars(select(KnowledgeReview).where(KnowledgeReview.document_id == control.id).order_by(KnowledgeReview.created_at, KnowledgeReview.id))]
    return data


def keywords(question):
    result = set(re.findall(r"[A-Za-z0-9_]+", question.casefold()))
    for run in re.findall(r"[\u3400-\u9fff]+", question):
        result.update(run[index:index + 2] for index in range(max(1, len(run) - 1)))
    return sorted(result)


def retrieve(db, actor, question):
    terms = keywords(question)
    scored = []
    for control, revision, audience in visible_publications(db, actor):
        title, body = revision.title.casefold(), revision.body.casefold()
        score = sum(3 * (term in title) + (term in body) for term in terms)
        if score:
            scored.append((score, control, revision, audience))
    scored.sort(key=lambda value: (-value[0], value[1].id))
    citations, sources = [], []
    for _score, control, revision, _audience in scored[:5]:
        sources.append((control.id, revision.id, control.access_epoch))
        for fragment in snippets(revision, terms):
            citations.append({**fragment, "document_id": control.id, "revision_id": revision.id, "document_version": revision.number, "title": revision.title, "source": revision.source, "access_epoch": control.access_epoch})
    return citations, sources


def register_knowledge(app, prefix, context, finish, audit, begin_idempotency, complete_idempotency, cas):
    def owned(db, actor, document_id):
        control = db.get(KnowledgeDocument, document_id)
        if not control or control.owner_id != actor.id:
            raise HTTPException(404, "记录不可访问")
        return control

    def active_members(db, member_ids):
        if member_ids:
            actual = set(db.scalars(select(User.id).where(User.id.in_(member_ids), User.active.is_(True))))
            if actual != set(member_ids):
                raise HTTPException(422, "固定受众包含无效成员")

    @app.get(prefix + "/knowledge/mine")
    def mine(ctx=Depends(context)):
        db, actor = ctx
        controls = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.owner_id == actor.id).order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id))
        return finish(db, [knowledge_detail(db, item) for item in controls])

    @app.get(prefix + "/knowledge/reviewers")
    def reviewers(ctx=Depends(context)):
        db, actor = ctx
        members = db.scalars(select(User).where(User.active.is_(True), User.id != actor.id, User.role.in_(("facilitator", "admin"))).order_by(User.display_name, User.id))
        return finish(db, [{"id": item.id, "display_name": item.display_name} for item in members])

    @app.get(prefix + "/knowledge/reviews")
    def review_queue(ctx=Depends(context)):
        db, actor = ctx
        result = []
        if actor.role in ("facilitator", "admin"):
            for control in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.reviewer_id == actor.id, KnowledgeDocument.submitted_revision_id.is_not(None)).order_by(KnowledgeDocument.updated_at.desc())):
                revision = revision_for(db, control, control.submitted_revision_id)
                if revision:
                    result.append({"id": control.id, "version": control.version, "owner_id": control.owner_id, "owner_name": db.get(User, control.owner_id).display_name, "revision": revision_data(revision)})
        return finish(db, result)

    @app.post(prefix + "/knowledge/answers")
    def answers(body: s.KnowledgeAnswerRequest, request: Request, ctx=Depends(context)):
        db, actor = ctx
        citations, sources = retrieve(db, actor, body.question)
        empty = {"mode": "insufficient", "answer": "目前没有足够的获准资料回答。请联系资料维护人或社区主持人核实；此查询不证明任何现行决定或任务状态。", "citations": [], "provider": None, "model": None}
        if not citations:
            return finish(db, empty)
        if not body.use_model:
            answer = "资料摘录，非模型回答。以下仅为已获准资料原文，不确认现行决定或任务状态：\n\n" + "\n\n".join(f"[{item['citation_id']}] {item['title']}：\n{item['quote']}" for item in citations[:6])
            return finish(db, {"mode": "extract", "answer": answer, "citations": citations[:6], "provider": None, "model": None})
        db.commit()  # No database writer lock is held while local inference runs.
        generated, error = None, None
        try:
            generated = app.state.ollama.answers(body.question, citations)
        except HTTPException as exc:
            error = exc
        db.expire_all()
        db, actor = context(request, db)
        # Recheck EVERY candidate source, including sources the model did not
        # cite. A source/ACL change invalidates this request's complete context.
        for document_id, revision_id, epoch in sorted(sources):
            # Lock candidate controls in a stable order during final validation
            # on PostgreSQL as well; SQLite already reserves its writer here.
            control = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id).with_for_update())
            current = current_publication(db, control, actor)
            if not current or current[0].id != revision_id or control.access_epoch != epoch:
                raise HTTPException(409, "资料版本或授权已变化，请重新查询")
        if error:
            raise error
        try:
            validated = s.ModelKnowledgeAnswer.model_validate(generated, strict=True)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(503, "本地回答格式无效，请查看资料摘录")
        available = {item["citation_id"]: item for item in citations}
        if any(key not in available for key in validated.citation_ids):
            raise HTTPException(503, "本地回答引用无效，请查看资料摘录")
        if not validated.answer.strip():
            return finish(db, empty)
        return finish(db, {"mode": "local_model", "answer": validated.answer, "citations": [available[key] for key in validated.citation_ids], "provider": "ollama", "model": app.state.ollama.model})

    @app.post(prefix + "/knowledge")
    def create(body: s.KnowledgeFields, ctx=Depends(context)):
        db, actor = ctx
        active_members(db, body.requested_member_ids)
        document_id, revision_id, now = uid(), uid(), stamp()
        control = KnowledgeDocument(id=document_id, owner_id=actor.id, latest_revision_id=revision_id, created_at=now, updated_at=now)
        db.add(control)
        db.flush()
        revision = KnowledgeRevision(id=revision_id, document_id=document_id, number=1, created_at=now, **body.model_dump())
        db.add(revision)
        db.flush()
        audit(db, actor, "knowledge.create", "knowledge", document_id, control.version)
        return finish(db, knowledge_detail(db, control))

    @app.get(prefix + "/knowledge/{document_id}")
    def private_detail(document_id: str, ctx=Depends(context)):
        db, actor = ctx
        return finish(db, knowledge_detail(db, owned(db, actor, document_id)))

    @app.patch(prefix + "/knowledge/{document_id}")
    def edit(document_id: str, body: s.KnowledgePatch, ctx=Depends(context)):
        db, actor = ctx
        control = owned(db, actor, document_id)
        active_members(db, body.requested_member_ids)
        previous = revision_for(db, control, control.latest_revision_id)
        if not previous:
            raise HTTPException(409, "资料版本元数据不完整")
        revision_id, now = uid(), stamp()
        cas(db, KnowledgeDocument, control, body.object_version, {"version": body.object_version + 1, "latest_revision_id": revision_id, "submitted_revision_id": None, "reviewer_id": None, "updated_at": now})
        values = body.model_dump(exclude={"object_version"})
        db.add(KnowledgeRevision(id=revision_id, document_id=control.id, number=previous.number + 1, created_at=now, **values))
        db.flush()
        audit(db, actor, "knowledge.edit", "knowledge", control.id, control.version)
        return finish(db, knowledge_detail(db, control))

    @app.post(prefix + "/knowledge/{document_id}/submit")
    def submit(document_id: str, body: s.KnowledgeSubmit, request: Request, ctx=Depends(context)):
        db, actor = ctx
        control = owned(db, actor, document_id)
        reviewer = db.get(User, body.reviewer_id)
        if not reviewer or not reviewer.active or reviewer.role not in ("facilitator", "admin") or reviewer.id == actor.id:
            raise HTTPException(422, "请选择另一位当前有效审核人")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, knowledge_detail(db, control))
        if body.revision_id != control.latest_revision_id or not revision_for(db, control, body.revision_id):
            raise HTTPException(409, "只能提交当前最新完整版本")
        approved = db.scalar(select(KnowledgeReview.id).where(KnowledgeReview.document_id == control.id, KnowledgeReview.revision_id == body.revision_id, KnowledgeReview.decision == "approve"))
        if approved:
            raise HTTPException(409, "该内容版本已审核发布；重新发布或扩大受众须另存完整新版本再送审")
        cas(db, KnowledgeDocument, control, body.object_version, {"version": body.object_version + 1, "submitted_revision_id": body.revision_id, "reviewer_id": reviewer.id, "updated_at": stamp()})
        audit(db, actor, "knowledge.submit", "knowledge", control.id, control.version)
        return complete_idempotency(db, record, knowledge_detail(db, control))

    @app.post(prefix + "/knowledge/{document_id}/cancel-submission")
    def cancel_submission(document_id: str, body: s.Version, request: Request, ctx=Depends(context)):
        db, actor = ctx
        control = owned(db, actor, document_id)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, knowledge_detail(db, control))
        if not control.submitted_revision_id:
            raise HTTPException(422, "没有当前送审可撤回")
        cas(db, KnowledgeDocument, control, body.object_version, {"version": body.object_version + 1, "submitted_revision_id": None, "reviewer_id": None, "updated_at": stamp()})
        audit(db, actor, "knowledge.cancel_submission", "knowledge", control.id, control.version)
        return complete_idempotency(db, record, knowledge_detail(db, control))

    @app.post(prefix + "/knowledge/{document_id}/review")
    def review(document_id: str, body: s.KnowledgeReviewRequest, request: Request, ctx=Depends(context)):
        db, actor = ctx
        control = db.get(KnowledgeDocument, document_id)
        if not control or control.reviewer_id != actor.id or control.owner_id == actor.id or actor.role not in ("facilitator", "admin"):
            raise HTTPException(404, "记录不可访问")
        submitted = control.submitted_revision_id == body.revision_id
        completed = db.scalar(select(KnowledgeReview.id).where(KnowledgeReview.document_id == control.id, KnowledgeReview.revision_id == body.revision_id, KnowledgeReview.reviewer_id == actor.id))
        if not submitted and not completed:
            raise HTTPException(404, "记录不可访问")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            # This receipt contains no draft/publication body or audience list.
            return finish(db, replay)
        if not submitted:
            raise HTTPException(409, "该版本已完成审核；请刷新审核队列")
        revision = revision_for(db, control, body.revision_id)
        if not revision:
            raise HTTPException(404, "记录不可访问")
        approved = db.scalar(select(KnowledgeReview.id).where(KnowledgeReview.document_id == control.id, KnowledgeReview.revision_id == revision.id, KnowledgeReview.decision == "approve"))
        if approved:
            raise HTTPException(409, "该内容版本已经发布；须由作者另存新版本后重新送审")
        values = {"version": body.object_version + 1, "submitted_revision_id": None, "updated_at": stamp()}
        if body.decision == "approve":
            if not unexpired(revision):
                raise HTTPException(422, "已过有效期的资料不能发布")
            active_members(db, revision.requested_member_ids)
            values.update(published_revision_id=revision.id, access_epoch=control.access_epoch + 1, withdrawn_at=None)
        cas(db, KnowledgeDocument, control, body.object_version, values)
        db.add(KnowledgeReview(document_id=control.id, revision_id=revision.id, reviewer_id=actor.id, decision=body.decision, reason=body.reason, created_at=stamp()))
        if body.decision == "approve":
            audience = db.get(KnowledgeAudience, control.id)
            if not audience:
                audience = KnowledgeAudience(document_id=control.id, revision_id=revision.id, scope=revision.requested_scope, member_ids=list(revision.requested_member_ids))
                db.add(audience)
            else:
                audience.revision_id, audience.scope, audience.member_ids = revision.id, revision.requested_scope, list(revision.requested_member_ids)
            snapshot = db.get(Document, control.id)
            if not snapshot:
                snapshot = Document(id=control.id)
                db.add(snapshot)
            for key in ("title", "category", "body", "source"):
                setattr(snapshot, key, getattr(revision, key))
            snapshot.version, snapshot.updated_at = revision.number, stamp()
        db.flush()
        audit(db, actor, "knowledge." + body.decision, "knowledge", control.id, control.version)
        return complete_idempotency(db, record, {"ok": True, "id": control.id, "version": control.version, "decision": body.decision})

    @app.post(prefix + "/knowledge/{document_id}/withdraw")
    def withdraw(document_id: str, body: s.Version, request: Request, ctx=Depends(context)):
        db, actor = ctx
        control = owned(db, actor, document_id)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, knowledge_detail(db, control))
        if not control.published_revision_id or control.withdrawn_at:
            raise HTTPException(422, "没有当前发布资料可撤下")
        cas(db, KnowledgeDocument, control, body.object_version, {"version": body.object_version + 1, "withdrawn_at": stamp(), "access_epoch": control.access_epoch + 1, "submitted_revision_id": None, "reviewer_id": None, "updated_at": stamp()})
        audit(db, actor, "knowledge.withdraw", "knowledge", control.id, control.version)
        return complete_idempotency(db, record, knowledge_detail(db, control))

    @app.post(prefix + "/knowledge/{document_id}/restrict")
    def restrict(document_id: str, body: s.KnowledgeRestrict, request: Request, ctx=Depends(context)):
        db, actor = ctx
        control = owned(db, actor, document_id)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, knowledge_detail(db, control))
        publication = current_publication(db, control, actor)
        if not publication:
            raise HTTPException(422, "没有当前有效发布资料可收紧")
        _revision, audience = publication
        active_members(db, body.member_ids)
        if audience.scope == "members" and not set(body.member_ids).issubset(audience.member_ids):
            raise HTTPException(422, "此操作只能减少现有受众；扩大范围须重新送审")
        cas(db, KnowledgeDocument, control, body.object_version, {"version": body.object_version + 1, "access_epoch": control.access_epoch + 1, "submitted_revision_id": None, "reviewer_id": None, "updated_at": stamp()})
        audience.scope, audience.member_ids = "members", list(body.member_ids)
        db.flush()
        audit(db, actor, "knowledge.restrict", "knowledge", control.id, control.version)
        return complete_idempotency(db, record, knowledge_detail(db, control))

    @app.get(prefix + "/documents/{document_id}")
    def document_detail(document_id: str, revision_id: str | None = None, ctx=Depends(context)):
        db, actor = ctx
        control = db.get(KnowledgeDocument, document_id)
        publication = current_publication(db, control, actor)
        if not publication or (revision_id is not None and revision_id != publication[0].id):
            raise HTTPException(404, "记录不可访问")
        return finish(db, published_data(db, control, *publication))
