"""Independent API-boundary tests using isolated, synthetic SQLite data."""

import concurrent.futures
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from symsoil_api.main import create_app
from symsoil_api.models import User, Audit
from symsoil_api.security import password_hasher


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('SYMSOIL_MODE', 'development')
    monkeypatch.setenv('SYMSOIL_COOKIE_SECURE', 'false')
    monkeypatch.setenv('SYMSOIL_SESSION_IDLE_MINUTES', '5')
    monkeypatch.delenv('SYMSOIL_ALLOWED_ORIGINS', raising=False)
    app = create_app(f'sqlite:///{tmp_path}/review.db')
    users = {}
    encoded_password = password_hasher.hash('review-password-123')
    with app.state.session_factory() as db:
        for name, role in [('admin', 'admin'), ('host', 'facilitator'), ('alice', 'member'), ('bob', 'member'), ('outsider', 'member')]:
            user = User(username=name, display_name=name, role=role, active=True, password_hash=encoded_password)
            db.add(user)
            db.flush()
            users[name] = user.id
        db.commit()
    clients = {}
    for name in users:
        client = TestClient(app)
        login = client.post('/api/v1/auth/login', json={'username': name, 'password': 'review-password-123'})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        clients[name] = client
    topic = clients['host'].post('/api/v1/topics', json={'title': 'synthetic review', 'description': 'review only', 'scope': 'synthetic-only'}).json()
    for name in ['alice', 'bob']:
        topic = clients['host'].post(f"/api/v1/topics/{topic['id']}/participants", json={'member_id': users[name], 'object_version': topic['version']}).json()
    return app, users, clients, topic


def new_utterance(clients):
    return clients['alice'].post('/api/v1/utterances', json={'title': 'private', 'text': 'private draft'}).json()


def test_csrf_origin_and_actor_spoof(env):
    _, users, clients, _ = env
    c = clients['alice']
    token = c.headers.pop('X-CSRF-Token')
    assert c.post('/api/v1/utterances', json={'title': 'test', 'text': 'test'}).status_code == 403
    c.headers['X-CSRF-Token'] = token
    assert c.post('/api/v1/utterances', headers={'Origin': 'https://attacker.example'}, json={'title': 'test', 'text': 'test'}).status_code == 403
    assert c.post('/api/v1/utterances', json={'title': 'test', 'text': 'test', 'author_id': users['admin']}).status_code == 422
    assert c.post('/api/v1/auth/login', headers={'Origin': 'https://attacker.example'}, json={'username':'alice','password':'review-password-123'}).status_code == 403


def test_object_acl_and_invitation_terms(env):
    _, users, clients, topic = env
    u = new_utterance(clients)
    for name in ['host', 'admin', 'bob']:
        assert clients[name].patch(f"/api/v1/utterances/{u['id']}", json={'title': 'overwrite', 'text':'overwrite','object_version':1}).status_code == 404
        assert u['id'] not in [i['id'] for i in clients[name].get('/api/v1/utterances').json()]
    for name in ['admin', 'outsider']:
        assert clients[name].get(f"/api/v1/topics/{topic['id']}").status_code == 404
    body = {'invitee_id':users['alice'],'title':'task','description':'private terms','completion_criteria':'specific done condition','resources':'private resource','compensation':'private compensation'}
    inv = clients['host'].post(f"/api/v1/topics/{topic['id']}/invitations", json=body).json()
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['invitations'] == []
    assert clients['bob'].get('/api/v1/invitations').json() == []
    for name in ['host', 'admin', 'bob']:
        assert clients[name].post(f"/api/v1/invitations/{inv['id']}/response", json={'object_version':1,'response':'accepted'}, headers={'Idempotency-Key':'recipient-only'}).status_code == 404


def test_confirm_share_versions_revoke_and_replay(env):
    _, _, clients, topic = env
    c = clients['alice']
    u = new_utterance(clients)
    base = f"/api/v1/utterances/{u['id']}"
    confirm = c.post(base+'/confirmations', json={'object_version':1}, headers={'Idempotency-Key':'confirm-v1'})
    assert confirm.status_code == 200
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints'] == []
    assert c.post(base+'/share', json={'object_version':1,'topic_id':topic['id']}, headers={'Idempotency-Key':'share-v1'}).status_code == 200
    assert len(clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints']) == 1
    assert c.post(base+'/revoke', json={'object_version':1}).status_code == 200
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints'] == []
    assert c.post(base+'/share', json={'object_version':1,'topic_id':topic['id']}, headers={'Idempotency-Key':'share-v1'}).status_code == 200
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints'] == []
    assert c.patch(base, json={'title':'private new','text':'changed private draft','object_version':1}).status_code == 200
    assert c.post(base+'/share', json={'object_version':2,'topic_id':topic['id']}, headers={'Idempotency-Key':'share-v2'}).status_code == 422
    assert c.post(base+'/confirmations', json={'object_version':1}, headers={'Idempotency-Key':'confirm-stale'}).status_code == 409


def test_stance_replay_cannot_restore_revoked_viewpoints(env):
    _, _, clients, topic = env
    u = new_utterance(clients)
    c = clients['alice']
    base = f"/api/v1/utterances/{u['id']}"
    c.post(base+'/confirmations', json={'object_version':1}, headers={'Idempotency-Key':'c'})
    c.post(base+'/share', json={'object_version':1,'topic_id':topic['id']}, headers={'Idempotency-Key':'s'})
    topic = clients['host'].post(f"/api/v1/topics/{topic['id']}/options", json={'title':'option','description':'desc','cost':'0','labor':'1','risks':'none','object_version':topic['version']}).json()
    option = topic['options'][0]
    stance_body = {'option_id':option['id'],'option_version':option['version'],'stance':'oppose','condition':''}
    url = f"/api/v1/topics/{topic['id']}/stances"
    assert len(clients['bob'].post(url, json=stance_body, headers={'Idempotency-Key':'stance'}).json()['viewpoints']) == 1
    c.post(base+'/revoke', json={'object_version':1})
    replay = clients['bob'].post(url, json=stance_body, headers={'Idempotency-Key':'stance'})
    assert replay.status_code == 200
    assert replay.json()['viewpoints'] == []


def test_conditional_missing_is_rejected(env):
    _, _, clients, topic = env
    topic = clients['host'].post(f"/api/v1/topics/{topic['id']}/options", json={'title':'option','description':'desc','cost':'0','labor':'1','risks':'none','object_version':topic['version']}).json()
    option = topic['options'][0]
    result = clients['alice'].post(f"/api/v1/topics/{topic['id']}/stances", json={'option_id':option['id'],'option_version':1,'stance':'conditional'}, headers={'Idempotency-Key':'missing-condition'})
    assert result.status_code == 422


def test_freeze_and_idempotency(env):
    app, users, clients, _ = env
    u = new_utterance(clients)
    url = f"/api/v1/utterances/{u['id']}/confirmations"
    for _ in range(2):
        assert clients['alice'].post(url, json={'object_version':1}, headers={'Idempotency-Key':'repeat'}).status_code == 200
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(Audit).where(Audit.actor_id==users['alice'],Audit.action=='utterance.confirm')))) == 1
    assert clients['alice'].post(url, json={'object_version':2}, headers={'Idempotency-Key':'repeat'}).status_code == 409
    assert clients['admin'].post(f"/api/v1/admin/members/{users['alice']}/freeze").status_code == 200
    assert clients['alice'].get('/api/v1/auth/me').status_code == 401
    assert clients['alice'].post(url, json={'object_version':1}, headers={'Idempotency-Key':'repeat'}).status_code == 401


def test_concurrent_version(env):
    _, _, clients, _ = env
    u = new_utterance(clients)
    def change(text):
        return clients['alice'].patch(f"/api/v1/utterances/{u['id']}", json={'title':'edit','text':text,'object_version':1}).status_code
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(change,['first','second']))
    assert sorted(results) == [200,409]


def test_static_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('SYMSOIL_MODE', 'development')
    monkeypatch.setenv('SYMSOIL_COOKIE_SECURE', 'false')
    dist = tmp_path/'dist'
    dist.mkdir()
    (dist/'index.html').write_text('<html>app</html>')
    (dist/'app.js').write_text('console.log("app")')
    app = create_app(f'sqlite:///{tmp_path}/static.db', str(dist))
    c = TestClient(app)
    assert c.get('/route').status_code == 200
    assert c.get('/app.js').status_code == 200
    assert c.get('/missing.js').status_code == 404
    assert c.get('/api/v1/missing').status_code == 404
    assert c.get('/api').status_code == 404
    assert c.get('/%2e%2e/private.txt').status_code == 404
