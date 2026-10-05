"""Independent R0.2 interface review; synthetic data only."""

import concurrent.futures
import threading

from sqlalchemy import select

from test_independent_security import env
from symsoil_api.models import ExpressionCandidate


def make_expression(clients, topic, confirm_original=True):
    c = clients['alice']
    u = c.post('/api/v1/utterances', json={'title':'private source','text':'PRIVATE ORIGINAL SOURCE'}).json()
    base = f"/api/v1/utterances/{u['id']}"
    detail = c.post(base+'/candidates', json={'object_version':1,'kind':'everyday','text':'ONLY SELECTED TRANSLATION','context':'PRIVATE CONTEXT','target_context':'PRIVATE TARGET','purpose':'PRIVATE PURPOSE'}).json()
    candidate = detail['candidates'][0]
    choice = c.post(base+'/choice', json={'object_version':1,'choice_version':0,'choice':'candidate','candidate_id':candidate['id'],'candidate_version':1}, headers={'Idempotency-Key':'choice-1'}).json()['choice']
    if confirm_original:
        assert c.post(base+'/confirmations', json={'object_version':1}, headers={'Idempotency-Key':'original-1'}).status_code == 200
    share = {'object_version':1,'topic_id':topic['id'],'representation':'candidate','candidate_id':candidate['id'],'candidate_version':1,'choice_version':choice['version']}
    return u, candidate, base, share


def test_candidate_choice_share_privacy_and_confirmation_prerequisites(env):
    _, _, clients, topic = env
    u, candidate, base, share = make_expression(clients, topic, False)
    c = clients['alice']
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints'] == []
    assert c.post(base+'/share', json=share, headers={'Idempotency-Key':'share-unconfirmed'}).status_code == 422
    c.post(base+'/confirmations', json={'object_version':1}, headers={'Idempotency-Key':'original-1'})
    assert c.post(base+'/share', json=share, headers={'Idempotency-Key':'share-1'}).status_code == 200
    for name in ['host','bob','admin']:
        assert clients[name].get(base+'/expression').status_code == 404
        assert clients[name].post(base+'/candidates', json={'object_version':1,'kind':'discussion','text':'x','context':'','target_context':'','purpose':''}).status_code == 404
    shared = clients['bob'].get(f"/api/v1/topics/{topic['id']}")
    assert shared.json()['viewpoints'][0]['text'] == 'ONLY SELECTED TRANSLATION'
    for private in ['PRIVATE ORIGINAL SOURCE','PRIVATE CONTEXT','PRIVATE TARGET','PRIVATE PURPOSE']:
        assert private not in shared.text


def test_candidate_edit_and_old_replay_cannot_restore_published_translation(env):
    _, _, clients, topic = env
    u, candidate, base, share = make_expression(clients, topic)
    c = clients['alice']
    assert c.post(base+'/share', json=share, headers={'Idempotency-Key':'share-1'}).status_code == 200
    detail = clients['host'].post(f"/api/v1/topics/{topic['id']}/options", json={'object_version':topic['version'],'title':'option','description':'desc','cost':'0','labor':'1','risks':'none'}).json()
    body = {'option_id':detail['options'][0]['id'],'option_version':1,'stance':'oppose','condition':''}
    stance_url = f"/api/v1/topics/{topic['id']}/stances"
    assert len(clients['bob'].post(stance_url, json=body, headers={'Idempotency-Key':'stance-1'}).json()['viewpoints']) == 1
    edited = c.patch(base+f"/candidates/{candidate['id']}", json={'object_version':1,'candidate_version':1,'text':'NEW PRIVATE TRANSLATION','context':'PRIVATE CONTEXT','target_context':'','purpose':''})
    assert edited.status_code == 200
    assert edited.json()['choice'] is None
    assert edited.json()['share'] is None
    assert edited.json()['candidates'][0]['confirmed_version'] is None
    assert clients['bob'].post(stance_url, json=body, headers={'Idempotency-Key':'stance-1'}).json()['viewpoints'] == []
    assert c.post(base+'/share', json=share, headers={'Idempotency-Key':'share-1'}).status_code == 200
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints'] == []
    assert c.patch(base,json={'object_version':1,'title':'source new','text':'NEW ORIGINAL'}).status_code == 200
    current = c.get(base+'/expression').json()
    assert current['candidates'] == [] and current['choice'] is None and current['share'] is None
    assert c.patch(base+f"/candidates/{candidate['id']}",json={'object_version':2,'candidate_version':2,'text':'attempt','context':'','target_context':'','purpose':''}).status_code == 404


def test_candidate_limit_and_choice_version(env):
    _, _, clients, topic = env
    _, candidate, base, share = make_expression(clients, topic)
    c = clients['alice']
    second = {'object_version':1,'kind':'discussion','text':'SECOND PRIVATE CANDIDATE','context':'','target_context':'','purpose':''}
    assert c.post(base+'/candidates',json=second).status_code == 200
    assert c.post(base+'/candidates',json=second).status_code == 409
    assert c.post(base+'/candidates',json={**second,'kind':'third'}).status_code == 422
    assert c.post(base+'/candidates',json={**second,'origin':'local_model'}).status_code == 422
    c.post(base+'/share',json=share,headers={'Idempotency-Key':'share-1'})
    reject = {'object_version':1,'choice_version':1,'choice':'no_rephrase'}
    changed = c.post(base+'/choice',json=reject,headers={'Idempotency-Key':'reject'}).json()
    assert changed['choice']['choice'] == 'no_rephrase' and changed['share'] is None
    assert clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()['viewpoints'] == []
    assert c.post(base+'/choice',json={**reject,'choice':'original_only'},headers={'Idempotency-Key':'stale-choice'}).status_code == 409
    assert c.post(base+'/choice',json={**reject,'choice_version':2,'candidate_id':candidate['id']},headers={'Idempotency-Key':'illegal-choice'}).status_code == 422


def make_understanding(clients, topic, base, share):
    clients['alice'].post(base+'/share',json=share,headers={'Idempotency-Key':'share-1'})
    body = {'utterance_id':base.split('/')[4], 'utterance_version':1,'representation':'candidate','candidate_id':share['candidate_id'],'candidate_version':1,'text':'PRIVATE LISTENER UNDERSTANDING'}
    url = f"/api/v1/topics/{topic['id']}/understandings"
    result = clients['bob'].post(url,json=body,headers={'Idempotency-Key':'understanding-1'})
    assert result.status_code == 200
    return result.json(), body, url


def test_understanding_both_party_privacy_author_response_and_no_support(env):
    _, _, clients, topic = env
    _, _, base, share = make_expression(clients, topic)
    item, body, url = make_understanding(clients,topic,base,share)
    assert clients['alice'].post(url,json=body,headers={'Idempotency-Key':'self'}).status_code == 422
    response_url = f"/api/v1/understandings/{item['id']}/response"
    response_body = {'object_version':1,'status':'accurate','correction':''}
    for name in ['host','admin','bob']:
        assert clients[name].post(response_url,json=response_body,headers={'Idempotency-Key':'not-author'}).status_code == 404
    for name in ['host','admin']:
        assert clients[name].get('/api/v1/understandings').json() == []
    topic_before = clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()
    assert 'PRIVATE LISTENER UNDERSTANDING' not in str(topic_before)
    assert clients['alice'].post(response_url,json={'object_version':1,'status':'needs_correction','correction':' '},headers={'Idempotency-Key':'empty-correction'}).status_code == 422
    assert clients['alice'].post(response_url,json=response_body,headers={'Idempotency-Key':'author-response'}).json()['status'] == 'accurate'
    topic_after = clients['bob'].get(f"/api/v1/topics/{topic['id']}").json()
    assert topic_after == topic_before
    assert clients['bob'].get('/api/v1/understandings').json()[0]['status'] == 'accurate'


def test_understanding_source_withdrawal_representation_and_cached_response(env):
    _, _, clients, topic = env
    _, _, base, share = make_expression(clients,topic)
    item, body, url = make_understanding(clients,topic,base,share)
    response_url = f"/api/v1/understandings/{item['id']}/response"
    response_body = {'object_version':1,'status':'prefer_in_person','correction':''}
    assert clients['alice'].post(response_url,json=response_body,headers={'Idempotency-Key':'respond-1'}).status_code == 200
    clients['alice'].post(base+'/revoke',json={'object_version':1})
    for name in ['alice','bob']:
        assert clients[name].get('/api/v1/understandings').json() == []
    assert clients['bob'].post(url,json=body,headers={'Idempotency-Key':'understanding-1'}).status_code == 404
    assert clients['alice'].post(response_url,json=response_body,headers={'Idempotency-Key':'respond-1'}).status_code == 404
    assert clients['alice'].post(base+'/share',json=share,headers={'Idempotency-Key':'share-again'}).status_code == 200
    assert clients['bob'].get('/api/v1/understandings').json()[0]['status'] == 'prefer_in_person'
    assert clients['alice'].post(base+'/share',json={'object_version':1,'topic_id':topic['id'],'representation':'original'},headers={'Idempotency-Key':'switch-original'}).status_code == 200
    assert clients['bob'].get('/api/v1/understandings').json() == []
    assert clients['alice'].post(response_url,json=response_body,headers={'Idempotency-Key':'respond-1'}).status_code == 404


class PausedModel:
    """A synthetic in-process adapter for authorization races, never inference."""
    model = 'synthetic-race-fixture'

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def suggestions(self, *_arguments):
        self.started.set()
        assert self.release.wait(5), 'test did not release synthetic generation'
        return {'candidates':[{'kind':'everyday','text':'PRIVATE MODEL PREVIEW'}],'clarifications':[]}


def test_generation_return_rechecks_freeze_and_does_not_persist_candidates(env):
    app, users, clients, _ = env
    model = PausedModel()
    app.state.ollama = model
    u = clients['alice'].post('/api/v1/utterances',json={'title':'race source','text':'PRIVATE ORIGINAL FOR MODEL'}).json()
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        pending = pool.submit(clients['alice'].post, f"/api/v1/utterances/{u['id']}/suggestions", json={'object_version':1,'context':'','target_context':'','purpose':''})
        try:
            assert model.started.wait(5)
            # If the model call still held SQLite's write lock this operation
            # could not succeed while the synthetic model was paused.
            assert clients['admin'].post(f"/api/v1/admin/members/{users['alice']}/freeze").status_code == 200
        finally:
            model.release.set()
        result = pending.result(timeout=5)
    assert result.status_code == 401
    assert 'PRIVATE MODEL PREVIEW' not in result.text
    with app.state.session_factory() as db:
        assert list(db.scalars(select(ExpressionCandidate).where(ExpressionCandidate.utterance_id==u['id']))) == []


def test_generation_return_rechecks_original_version(env):
    app, _, clients, _ = env
    model = PausedModel()
    app.state.ollama = model
    u = clients['alice'].post('/api/v1/utterances',json={'title':'race source','text':'OLD PRIVATE ORIGINAL'}).json()
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        pending = pool.submit(clients['alice'].post, f"/api/v1/utterances/{u['id']}/suggestions", json={'object_version':1,'context':'','target_context':'','purpose':''})
        try:
            assert model.started.wait(5)
            assert clients['alice'].patch(f"/api/v1/utterances/{u['id']}",json={'object_version':1,'title':'updated source','text':'NEW PRIVATE ORIGINAL'}).status_code == 200
        finally:
            model.release.set()
        result = pending.result(timeout=5)
    assert result.status_code == 409
    assert 'PRIVATE MODEL PREVIEW' not in result.text
    with app.state.session_factory() as db:
        assert list(db.scalars(select(ExpressionCandidate).where(ExpressionCandidate.utterance_id==u['id']))) == []
