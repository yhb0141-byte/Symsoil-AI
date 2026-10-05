import hashlib
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import select

from .models import Session, User

password_hasher = PasswordHasher()
COOKIE_NAME = "symsoil_session"


def utcnow():
    return datetime.now(timezone.utc)


def stamp(moment=None):
    return (moment or utcnow()).isoformat().replace("+00:00", "Z")


def parse_stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded, password):
    try:
        return password_hasher.verify(encoded, password)
    except VerificationError:
        return False


def secure_cookie():
    secure = os.getenv("SYMSOIL_COOKIE_SECURE", "false").lower() == "true"
    if os.getenv("SYMSOIL_MODE", "development") == "production" and not secure:
        raise RuntimeError("production requires SYMSOIL_COOKIE_SECURE=true and HTTPS")
    return secure


def require_origin(request: Request):
    origin = request.headers.get("origin")
    if not origin:
        return
    configured = [item.strip().rstrip("/") for item in os.getenv("SYMSOIL_ALLOWED_ORIGINS", "").split(",") if item.strip()]
    expected = configured or [f"{request.url.scheme}://{request.url.netloc}"]
    parsed = urlparse(origin)
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or origin.rstrip("/") not in expected:
        raise HTTPException(403, "请求来源不受信任")


def authenticate(db, request):
    token = request.cookies.get(COOKIE_NAME, "")
    session = db.scalar(select(Session).where(Session.token_hash == digest(token))) if token else None
    if not session or session.revoked:
        raise HTTPException(401, "请重新登录")
    user = db.get(User, session.user_id)
    idle_seconds = int(os.getenv("SYMSOIL_SESSION_IDLE_MINUTES", "5")) * 60
    now = utcnow()
    if not user or not user.active or now >= parse_stamp(session.expires_at) or (now - parse_stamp(session.last_seen_at)).total_seconds() >= idle_seconds:
        session.revoked = True
        db.commit()
        raise HTTPException(401, "会话已失效，请重新登录")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        require_origin(request)
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not secrets.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, "CSRF校验失败")
    # The guarded SQL write at final commit must not resurrect a revoked session.
    request.state.auth_session = session
    request.state.user = user
    return user
