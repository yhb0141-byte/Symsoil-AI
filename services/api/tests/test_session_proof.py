"""Cookie-only reads must fail after browser in-memory proof is cleared."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request

from symsoil_api.main import create_app
from symsoil_api.models import Session, User
from symsoil_api.security import COOKIE_NAME, authenticate, digest, password_hasher


PRIVATE_READS = (
    "/api/v1/auth/me",
    "/api/v1/utterances",
    "/api/v1/topics",
    "/api/v1/audit",
)


@pytest.fixture
def proof_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SYMSOIL_MODE", "development")
    monkeypatch.setenv("SYMSOIL_COOKIE_SECURE", "false")
    monkeypatch.setenv("SYMSOIL_SESSION_IDLE_MINUTES", "5")
    monkeypatch.delenv("SYMSOIL_ALLOWED_ORIGINS", raising=False)
    app = create_app(f"sqlite:///{tmp_path}/proof.db")
    with app.state.session_factory() as db:
        encoded = password_hasher.hash("synthetic-review-password")
        db.add_all([
            User(username="owner", display_name="Synthetic owner", role="member", active=True, password_hash=encoded),
            User(username="other", display_name="Synthetic other", role="member", active=True, password_hash=encoded),
        ])
        db.commit()
    clients, proofs = {}, {}
    for name in ("owner", "other"):
        client = TestClient(app)
        response = client.post("/api/v1/auth/login", json={"username": name, "password": "synthetic-review-password"})
        assert response.status_code == 200
        proofs[name] = response.json()["csrf_token"]
        assert len(proofs[name]) == 64
        clients[name] = client
    return app, clients, proofs


@pytest.mark.parametrize("path", PRIVATE_READS)
def test_cookie_alone_cannot_read_or_bootstrap_proof(proof_env, path):
    _, clients, _ = proof_env
    response = clients["owner"].get(path)
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}
    assert "csrf_token" not in response.text
    assert "Synthetic owner" not in response.text


@pytest.mark.parametrize("path", PRIVATE_READS)
def test_correct_in_memory_proof_allows_read(proof_env, path):
    _, clients, proofs = proof_env
    response = clients["owner"].get(path, headers={"X-CSRF-Token": proofs["owner"]})
    assert response.status_code == 200
    if path == "/api/v1/auth/me":
        assert response.json()["csrf_token"] == proofs["owner"]


def test_missing_cookie_and_wrong_session_proof_are_unauthorized(proof_env):
    app, clients, proofs = proof_env
    assert TestClient(app).get("/api/v1/auth/me", headers={"X-CSRF-Token": proofs["owner"]}).status_code == 401
    assert clients["owner"].get("/api/v1/auth/me", headers={"X-CSRF-Token": proofs["other"]}).status_code == 401
    assert clients["owner"].get("/api/v1/auth/me", headers={"X-CSRF-Token": "invalid"}).status_code == 401


def test_mutations_without_proof_keep_csrf_403(proof_env):
    _, clients, proofs = proof_env
    for supplied in ({}, {"X-CSRF-Token": proofs["other"]}):
        assert clients["owner"].post("/api/v1/utterances", json={"title": "Synthetic private", "text": "Private draft"}, headers=supplied).status_code == 403


def test_clearing_proof_blocks_live_cookie_after_offline_logout(proof_env):
    app, clients, proofs = proof_env
    client = clients["owner"]
    client.headers["X-CSRF-Token"] = proofs["owner"]
    saved = client.post("/api/v1/utterances", json={"title": "Synthetic secret", "text": "Unshared private text"})
    assert saved.status_code == 200
    assert client.get("/api/v1/utterances").json()[0]["text"] == "Unshared private text"
    cookie = client.cookies.get(COOKIE_NAME)
    client.headers.pop("X-CSRF-Token")
    # No logout reaches the server: its session and cookie intentionally remain
    # active. The next person nevertheless cannot derive or read the old proof.
    with app.state.session_factory() as db:
        session = db.scalar(select(Session).where(Session.token_hash == digest(cookie)))
        assert not session.revoked
    for path in PRIVATE_READS:
        response = client.get(path)
        assert response.status_code == 401
        assert "Unshared private text" not in response.text
    assert client.cookies.get(COOKIE_NAME) == cookie


def test_head_authentication_also_requires_proof(proof_env):
    app, clients, proofs = proof_env
    cookie = clients["owner"].cookies.get(COOKIE_NAME)
    scope = {"type": "http", "method": "HEAD", "path": "/api/v1/utterances", "headers": [(b"cookie", f"{COOKIE_NAME}={cookie}".encode())]}
    with app.state.session_factory() as db:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error:
            authenticate(db, Request(scope))
        assert error.value.status_code == 401
        scope["headers"].append((b"x-csrf-token", proofs["owner"].encode()))
        assert authenticate(db, Request(scope)).username == "owner"


def test_non_ascii_invalid_proof_returns_401_instead_of_server_error(proof_env):
    _, clients, _ = proof_env
    response = clients["owner"].get("/api/v1/auth/me", headers=[(b"X-CSRF-Token", b"\xff")])
    assert response.status_code == 401
