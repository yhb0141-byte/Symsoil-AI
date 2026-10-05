import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import schemas as s
from .db import Base, database_url, make_engine, session_factory
from .models import Audit, Document, Idempotency, Invitation, Option, Participant, RegistrationInvite, Session, Stance, Topic, User, Utterance
from .security import COOKIE_NAME, authenticate, digest, password_hasher, require_origin, secure_cookie, stamp, utcnow, verify_password
from .serialize import document_data, invitation_data, topic_data, topic_detail, user_data, utterance_data, viewpoint_data


def create_app(url: str | None = None, web_dist: str | None = None):
    app = FastAPI(title="SymSoil R0 API", version="0.1.0")
    engine = make_engine(url or database_url())
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.cookie_secure = secure_cookie()

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        # Do not echo submitted passwords, private drafts, or invalid field values.
        fields = ", ".join(".".join(str(part) for part in error["loc"][1:]) for error in exc.errors())
        return JSONResponse(status_code=422, content={"detail": f"输入格式不正确：{fields}"})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)}, headers=exc.headers)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def database():
        with factory() as db:
            try:
                yield db
            finally:
                db.rollback()

    def context(request: Request, db=Depends(database)):
        actor = authenticate(db, request)
        # Acquire the write transaction before business reads, and condition it on
        # current account/session state. Freezing cannot be undone by a stale ORM row.
        changed = db.execute(update(Session).where(
            Session.id == request.state.auth_session.id, Session.revoked.is_(False),
            exists(select(User.id).where(User.id == Session.user_id, User.active.is_(True))),
        ).values(last_seen_at=stamp())).rowcount
        if changed != 1:
            raise HTTPException(401, "会话已失效，请重新登录")
        return db, actor

    def finish(db, data):
        db.commit()
        return data

    def audit(db, actor, action, kind, item_id, version=None):
        db.add(Audit(actor_id=actor.id, action=action, object_type=kind, object_id=item_id, object_version=version, created_at=stamp()))

    def owned_utterance(db, actor, item_id):
        item = db.get(Utterance, item_id)
        if not item or item.author_id != actor.id:
            raise HTTPException(404, "记录不可访问")
        return item

    def accessible_topic(db, actor, topic_id, owner=False):
        topic = db.get(Topic, topic_id)
        if not topic or not db.get(Participant, (topic_id, actor.id)) or (owner and topic.owner_id != actor.id):
            raise HTTPException(404, "记录不可访问")
        return topic

    def visible_invitation(db, actor, item_id, recipient=False):
        item = db.get(Invitation, item_id)
        if not item or (item.invitee_id != actor.id if recipient else actor.id not in (item.invitee_id, item.issuer_id)):
            raise HTTPException(404, "记录不可访问")
        return item

    def check_version(item, version):
        if item.version != version:
            raise HTTPException(409, "版本已变化，请刷新后重新核对")

    def cas(db, model, item, version, values, *extra):
        changed = db.execute(update(model).where(model.id == item.id, model.version == version, *extra).values(**values)).rowcount
        if changed != 1:
            raise HTTPException(409, "版本或状态已变化，请刷新后重新核对")
        db.refresh(item)

    def begin_idempotency(db, actor, request, body):
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 100 or not all(32 <= ord(char) < 127 for char in key):
            raise HTTPException(422, "该操作需要有效的Idempotency-Key")
        operation = request.method + " " + request.url.path
        payload_hash = digest(json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        criteria = (Idempotency.actor_id == actor.id, Idempotency.operation == operation, Idempotency.key == key)
        previous = db.scalar(select(Idempotency).where(*criteria))
        if previous:
            if previous.payload_hash != payload_hash:
                raise HTTPException(409, "幂等键已经用于另一份请求")
            return previous, previous.result
        record = Idempotency(actor_id=actor.id, operation=operation, key=key, payload_hash=payload_hash, created_at=stamp())
        db.add(record)
        # The session guard serializes SQLite writes; the uniqueness constraint
        # also protects PostgreSQL. The reservation and effect commit together.
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            # This request lost a concurrent reservation. Rollback also releases
            # the authenticated guard; ask for a clean retry rather than replay
            # under stale account or object permissions.
            raise HTTPException(409, "并发请求已提交，请使用同一幂等键重试")
        return record, None

    def complete_idempotency(db, record, data):
        record.result = data
        return finish(db, data)

    def safe_topic_replay(db, replay, topic_id):
        # A cached mutation result must not resurrect an expression whose author
        # has since withdrawn it or changed the original version.
        permitted = {(item.id, item.shared_version) for item in db.scalars(select(Utterance).where(Utterance.shared_topic_id == topic_id, Utterance.shared_version == Utterance.version, Utterance.confirmed_version == Utterance.version))}
        replay = dict(replay)
        replay["viewpoints"] = [item for item in replay.get("viewpoints", []) if (item["id"], item["utterance_version"]) in permitted]
        return replay

    prefix = "/api/v1"

    @app.get(prefix + "/health")
    def health():
        return {"status": "ok", "stage": "R0", "ai_available": False}

    @app.post(prefix + "/auth/login")
    def login(body: s.Login, request: Request, response: Response, db=Depends(database)):
        require_origin(request)
        actor = db.scalar(select(User).where(User.username == body.username))
        if not actor or not actor.active or not verify_password(actor.password_hash, body.password):
            raise HTTPException(401, "账号或口令不正确")
        token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
        now = utcnow()
        session = Session(user_id=actor.id, token_hash=digest(token), csrf_token=csrf, created_at=stamp(now), last_seen_at=stamp(now), expires_at=stamp(now + timedelta(hours=8)))
        db.add(session)
        audit(db, actor, "auth.login", "user", actor.id)
        db.commit()
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=app.state.cookie_secure, samesite="strict", path="/", max_age=8 * 60 * 60)
        return {"user": user_data(actor), "csrf_token": csrf}

    @app.get(prefix + "/auth/me")
    def me(request: Request, ctx=Depends(context)):
        db, actor = ctx
        return finish(db, {"user": user_data(actor), "csrf_token": request.state.auth_session.csrf_token})

    @app.post(prefix + "/auth/logout")
    def logout(request: Request, response: Response, ctx=Depends(context)):
        db, actor = ctx
        db.execute(update(Session).where(Session.id == request.state.auth_session.id).values(revoked=True))
        audit(db, actor, "auth.logout", "user", actor.id)
        response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=app.state.cookie_secure, samesite="strict")
        return finish(db, {"ok": True})

    @app.get(prefix + "/auth/sessions")
    def sessions(request: Request, ctx=Depends(context)):
        db, actor = ctx
        data = [{"id": item.id, "created_at": item.created_at, "last_seen_at": item.last_seen_at, "expires_at": item.expires_at, "revoked": item.revoked, "current": item.id == request.state.auth_session.id} for item in db.scalars(select(Session).where(Session.user_id == actor.id).order_by(Session.created_at.desc()))]
        return finish(db, data)

    @app.post(prefix + "/admin/invites")
    def admin_invite(body: s.AdminInvite, ctx=Depends(context)):
        db, actor = ctx
        if actor.role != "admin":
            raise HTTPException(403, "需要账号管理权限")
        if db.scalar(select(User.id).where(User.username == body.username)):
            raise HTTPException(409, "账号已存在")
        token = secrets.token_urlsafe(32)
        item = RegistrationInvite(token_hash=digest(token), issuer_id=actor.id, username=body.username, display_name=body.display_name, role=body.role, expires_at=stamp(utcnow() + timedelta(days=7)))
        db.add(item)
        db.flush()
        audit(db, actor, "registration.invite", "registration_invite", item.id)
        return finish(db, {"token": token, "expires_at": item.expires_at})

    @app.post(prefix + "/auth/register")
    def register(body: s.Register, request: Request, db=Depends(database)):
        require_origin(request)
        token_hash = digest(body.token)
        item = db.scalar(select(RegistrationInvite).where(RegistrationInvite.token_hash == token_hash))
        if not item or item.used or item.expires_at <= stamp():
            raise HTTPException(422, "注册邀请已失效")
        if db.scalar(select(User.id).where(User.username == item.username)):
            raise HTTPException(409, "账号已存在")
        changed = db.execute(update(RegistrationInvite).where(RegistrationInvite.id == item.id, RegistrationInvite.used.is_(False), RegistrationInvite.expires_at > stamp()).values(used=True)).rowcount
        if changed != 1:
            raise HTTPException(422, "注册邀请已失效")
        actor = User(username=item.username, display_name=item.display_name, role=item.role, active=True, password_hash=password_hasher.hash(body.password))
        db.add(actor)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "账号已存在")
        audit(db, actor, "auth.register", "user", actor.id)
        return finish(db, {"user": user_data(actor)})

    @app.get(prefix + "/admin/members")
    def admin_members(ctx=Depends(context)):
        db, actor = ctx
        if actor.role != "admin":
            raise HTTPException(403, "需要账号管理权限")
        return finish(db, [user_data(item) for item in db.scalars(select(User).order_by(User.username))])

    @app.post(prefix + "/admin/members/{member_id}/freeze")
    def freeze(member_id: str, ctx=Depends(context)):
        db, actor = ctx
        if actor.role != "admin":
            raise HTTPException(403, "需要账号管理权限")
        member = db.get(User, member_id)
        if not member:
            raise HTTPException(404, "记录不可访问")
        if member_id == actor.id:
            raise HTTPException(422, "R0不能冻结当前管理员本人")
        db.execute(update(User).where(User.id == member_id).values(active=False))
        db.execute(update(Session).where(Session.user_id == member_id).values(revoked=True))
        audit(db, actor, "member.freeze", "user", member_id)
        return finish(db, {"ok": True})

    @app.get(prefix + "/members")
    def members(ctx=Depends(context)):
        db, _actor = ctx
        return finish(db, [{"id": item.id, "display_name": item.display_name} for item in db.scalars(select(User).where(User.active.is_(True)).order_by(User.display_name))])

    @app.get(prefix + "/documents")
    def documents(q: str = "", ctx=Depends(context)):
        db, _actor = ctx
        if len(q) > 200:
            raise HTTPException(422, "检索文字过长")
        statement = select(Document).order_by(Document.title)
        if q.strip():
            # Escape LIKE metacharacters: the field is a literal keyword, not SQL.
            statement = statement.where(or_(Document.title.contains(q.strip(), autoescape=True), Document.body.contains(q.strip(), autoescape=True)))
        return finish(db, [document_data(item) for item in db.scalars(statement)])

    @app.get(prefix + "/utterances")
    def utterances(ctx=Depends(context)):
        db, actor = ctx
        return finish(db, [utterance_data(item) for item in db.scalars(select(Utterance).where(Utterance.author_id == actor.id).order_by(Utterance.updated_at.desc()))])

    @app.post(prefix + "/utterances")
    def create_utterance(body: s.UtteranceCreate, ctx=Depends(context)):
        db, actor = ctx
        item = Utterance(author_id=actor.id, title=body.title, text=body.text, created_at=stamp(), updated_at=stamp())
        db.add(item)
        db.flush()
        audit(db, actor, "utterance.create", "utterance", item.id, item.version)
        return finish(db, utterance_data(item))

    @app.patch(prefix + "/utterances/{item_id}")
    def edit_utterance(item_id: str, body: s.UtterancePatch, ctx=Depends(context)):
        db, actor = ctx
        item = owned_utterance(db, actor, item_id)
        cas(db, Utterance, item, body.object_version, {"title": body.title, "text": body.text, "version": body.object_version + 1, "confirmed_version": None, "confirmed_at": None, "shared_topic_id": None, "shared_version": None, "shared_text": None, "updated_at": stamp()})
        audit(db, actor, "utterance.edit", "utterance", item.id, item.version)
        return finish(db, utterance_data(item))

    @app.post(prefix + "/utterances/{item_id}/confirmations")
    def confirm_utterance(item_id: str, body: s.Version, request: Request, ctx=Depends(context)):
        db, actor = ctx
        item = owned_utterance(db, actor, item_id)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, replay)
        check_version(item, body.object_version)
        cas(db, Utterance, item, body.object_version, {"confirmed_version": item.version, "confirmed_at": stamp(), "updated_at": stamp()})
        audit(db, actor, "utterance.confirm", "utterance", item.id, item.version)
        return complete_idempotency(db, record, utterance_data(item))

    @app.post(prefix + "/utterances/{item_id}/share")
    def share_utterance(item_id: str, body: s.Share, request: Request, ctx=Depends(context)):
        db, actor = ctx
        item = owned_utterance(db, actor, item_id)
        accessible_topic(db, actor, body.topic_id)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, replay)
        check_version(item, body.object_version)
        if item.confirmed_version != item.version:
            raise HTTPException(422, "请先核对本版本，再主动分享原话")
        if item.shared_topic_id and item.shared_topic_id != body.topic_id:
            raise HTTPException(422, "请先撤回现有分享，再选择另一议题")
        cas(db, Utterance, item, body.object_version, {"shared_topic_id": body.topic_id, "shared_version": item.version, "shared_text": item.text, "updated_at": stamp()}, Utterance.confirmed_version == body.object_version)
        audit(db, actor, "utterance.share", "utterance", item.id, item.version)
        return complete_idempotency(db, record, viewpoint_data(db, item))

    @app.post(prefix + "/utterances/{item_id}/revoke")
    def revoke_utterance(item_id: str, body: s.Version, ctx=Depends(context)):
        db, actor = ctx
        item = owned_utterance(db, actor, item_id)
        cas(db, Utterance, item, body.object_version, {"shared_topic_id": None, "shared_version": None, "shared_text": None, "updated_at": stamp()})
        audit(db, actor, "utterance.revoke", "utterance", item.id, item.version)
        return finish(db, utterance_data(item))

    @app.get(prefix + "/topics")
    def topics(ctx=Depends(context)):
        db, actor = ctx
        items = db.scalars(select(Topic).join(Participant, Topic.id == Participant.topic_id).where(Participant.user_id == actor.id).order_by(Topic.created_at.desc()))
        return finish(db, [topic_data(db, item) for item in items])

    @app.post(prefix + "/topics")
    def create_topic(body: s.TopicCreate, ctx=Depends(context)):
        db, actor = ctx
        if actor.role not in ("admin", "facilitator"):
            raise HTTPException(403, "需要议题主持权限")
        item = Topic(owner_id=actor.id, title=body.title, description=body.description, scope=body.scope, created_at=stamp())
        db.add(item)
        db.flush()
        db.add(Participant(topic_id=item.id, user_id=actor.id))
        db.flush()
        audit(db, actor, "topic.create", "topic", item.id, item.version)
        return finish(db, topic_data(db, item))

    @app.get(prefix + "/topics/{topic_id}")
    def get_topic(topic_id: str, ctx=Depends(context)):
        db, actor = ctx
        item = accessible_topic(db, actor, topic_id)
        return finish(db, topic_detail(db, item, actor.id))

    @app.post(prefix + "/topics/{topic_id}/participants")
    def add_participant(topic_id: str, body: s.ParticipantAdd, ctx=Depends(context)):
        db, actor = ctx
        topic = accessible_topic(db, actor, topic_id, owner=True)
        check_version(topic, body.object_version)
        member = db.get(User, body.member_id)
        if not member or not member.active:
            raise HTTPException(404, "记录不可访问")
        if not db.get(Participant, (topic_id, body.member_id)):
            cas(db, Topic, topic, body.object_version, {"version": body.object_version + 1})
            db.add(Participant(topic_id=topic_id, user_id=body.member_id))
            db.flush()
            audit(db, actor, "topic.participant.add", "topic", topic.id, topic.version)
        return finish(db, topic_detail(db, topic, actor.id))

    @app.post(prefix + "/topics/{topic_id}/options")
    def add_option(topic_id: str, body: s.OptionCreate, ctx=Depends(context)):
        db, actor = ctx
        topic = accessible_topic(db, actor, topic_id)
        cas(db, Topic, topic, body.object_version, {"version": body.object_version + 1})
        item = Option(topic_id=topic_id, **body.model_dump(exclude={"object_version"}))
        db.add(item)
        db.flush()
        audit(db, actor, "topic.option.add", "option", item.id, item.version)
        return finish(db, topic_detail(db, topic, actor.id))

    @app.post(prefix + "/topics/{topic_id}/stances")
    def stance(topic_id: str, body: s.StanceCreate, request: Request, ctx=Depends(context)):
        db, actor = ctx
        topic = accessible_topic(db, actor, topic_id)
        option = db.get(Option, body.option_id)
        if not option or option.topic_id != topic_id:
            raise HTTPException(404, "记录不可访问")
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, safe_topic_replay(db, replay, topic_id))
        check_version(option, body.option_version)
        cas(db, Topic, topic, topic.version, {"version": topic.version + 1})
        item = db.get(Stance, (option.id, actor.id))
        if item:
            item.stance, item.condition, item.option_version = body.stance, body.condition, body.option_version
        else:
            db.add(Stance(option_id=option.id, member_id=actor.id, stance=body.stance, condition=body.condition, option_version=body.option_version))
        db.flush()
        audit(db, actor, "topic.stance", "option", option.id, option.version)
        return complete_idempotency(db, record, topic_detail(db, topic, actor.id))

    @app.get(prefix + "/invitations")
    def invitations(ctx=Depends(context)):
        db, actor = ctx
        items = db.scalars(select(Invitation).where(or_(Invitation.invitee_id == actor.id, Invitation.issuer_id == actor.id)).order_by(Invitation.created_at.desc()))
        return finish(db, [invitation_data(db, item) for item in items])

    @app.post(prefix + "/topics/{topic_id}/invitations")
    def create_invitation(topic_id: str, body: s.InvitationCreate, ctx=Depends(context)):
        db, actor = ctx
        topic = accessible_topic(db, actor, topic_id, owner=True)
        member = db.get(User, body.invitee_id)
        if not member or not member.active:
            raise HTTPException(404, "记录不可访问")
        cas(db, Topic, topic, topic.version, {"version": topic.version + 1})
        item = Invitation(topic_id=topic_id, issuer_id=actor.id, created_at=stamp(), **body.model_dump())
        db.add(item)
        db.flush()
        audit(db, actor, "task.invite", "invitation", item.id, item.version)
        return finish(db, invitation_data(db, item))

    @app.post(prefix + "/invitations/{item_id}/response")
    def invitation_response(item_id: str, body: s.InvitationResponse, request: Request, ctx=Depends(context)):
        db, actor = ctx
        item = visible_invitation(db, actor, item_id, recipient=True)
        record, replay = begin_idempotency(db, actor, request, body)
        if replay is not None:
            return finish(db, replay)
        check_version(item, body.object_version)
        if item.status not in ("pending", "negotiating"):
            raise HTTPException(422, "该邀请已结束，请由协调人另发邀请")
        cas(db, Invitation, item, body.object_version, {"status": body.response, "note": body.note, "version": body.object_version + 1}, Invitation.status.in_(("pending", "negotiating")))
        audit(db, actor, "task." + body.response, "invitation", item.id, item.version)
        return complete_idempotency(db, record, invitation_data(db, item))

    @app.get(prefix + "/audit")
    def audit_log(ctx=Depends(context)):
        db, actor = ctx
        items = db.scalars(select(Audit).where(Audit.actor_id == actor.id).order_by(Audit.created_at.desc()).limit(200))
        return finish(db, [{key: getattr(item, key) for key in ("id", "action", "object_type", "object_id", "object_version", "created_at")} for item in items])

    @app.get(prefix + "/dashboard")
    def dashboard(ctx=Depends(context)):
        db, actor = ctx
        topic_items = list(db.scalars(select(Topic).join(Participant, Topic.id == Participant.topic_id).where(Participant.user_id == actor.id).order_by(Topic.created_at.desc())))
        pending = list(db.scalars(select(Invitation).where(Invitation.invitee_id == actor.id, Invitation.status.in_(("pending", "negotiating"))).order_by(Invitation.created_at)))
        data = {"counts": {"topics": len(topic_items), "open_invitations": len(pending), "utterances": db.scalar(select(func.count()).select_from(Utterance).where(Utterance.author_id == actor.id)), "documents": db.scalar(select(func.count()).select_from(Document))}, "pending": [invitation_data(db, item) for item in pending], "topics": [topic_data(db, item) for item in topic_items], "ai": {"available": False}, "release": {"stage": "R0", "synthetic": True}}
        return finish(db, data)

    dist = Path(web_dist or os.getenv("SYMSOIL_WEB_DIST", "") or Path(__file__).resolve().parents[3] / "apps/web/dist").resolve()
    if dist.is_dir() and (dist / "index.html").is_file():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "接口不存在")
            candidate = (dist / path).resolve()
            if not candidate.is_relative_to(dist):
                raise HTTPException(404, "文件不存在")
            if candidate.is_file():
                return FileResponse(candidate)
            # Missing assets must be real 404s, never an HTML response masquerading as JS.
            if Path(path).suffix:
                raise HTTPException(404, "文件不存在")
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})
    return app


app = create_app()
