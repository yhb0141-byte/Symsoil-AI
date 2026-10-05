import pytest
from fastapi.testclient import TestClient

from symsoil_api.cli import seed_demo
from symsoil_api.main import create_app

PASSWORD = "only-test-password-2026"


@pytest.fixture
def harness(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with app.state.session_factory() as db:
        ids = seed_demo(db, PASSWORD)
    clients = []

    def login(username):
        client = TestClient(app)
        clients.append(client)
        response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return client

    yield app, ids, login
    for client in clients:
        client.close()
    app.state.engine.dispose()
