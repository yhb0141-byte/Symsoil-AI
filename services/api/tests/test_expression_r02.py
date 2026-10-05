import base64
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, update

from symsoil_api.main import create_app
from symsoil_api.models import ExpressionCandidate, ExpressionChoice, ExpressionShare, Session, Understanding, User
from symsoil_api.ollama import OllamaAdapter
from symsoil_api.security import stamp
from symsoil_api.suggestion_tokens import SuggestionSigner


def post(client, path, body, key="r02-key"):
    return client.post("/api/v1" + path, json=body, headers={"Idempotency-Key": key})


def original(client):
    return post(client, "/utterances", {"title": "私人原话", "text": "私人原话：我不能接受这个安排，也不会参加。"}).json()


def discussion(client):
    return client.get("/api/v1/topics").json()[0]


def candidate(client, item, kind="everyday", text="我不能接受目前的安排，也不会参加。"):
    response = post(client, f"/utterances/{item['id']}/candidates", {"object_version": item["version"], "kind": kind, "text": text, "context": "私人背景", "target_context": "私人目标语境", "purpose": "私人用途"})
    assert response.status_code == 200
    return next(value for value in response.json()["candidates"] if value["kind"] == kind)


def choose(client, item, value, choice_version=0, key="choose"):
    response = post(client, f"/utterances/{item['id']}/choice", {"object_version": item["version"], "choice_version": choice_version, "choice": "candidate", "candidate_id": value["id"], "candidate_version": value["version"]}, key)
    assert response.status_code == 200
    return response.json()


def shared_candidate(client):
    item = original(client)
    value = candidate(client, item)
    chosen = choose(client, item, value)
    post(client, f"/utterances/{item['id']}/confirmations", {"object_version": 1}, "confirm-original")
    topic = discussion(client)
    body = {"object_version": 1, "topic_id": topic["id"], "representation": "candidate", "candidate_id": value["id"], "candidate_version": 1, "choice_version": chosen["choice"]["version"]}
    shared = post(client, f"/utterances/{item['id']}/share", body, "share-candidate")
    assert shared.status_code == 200
    return item, value, topic, body


def comprehension(client, item, value, topic, key="understanding"):
    body = {"utterance_id": item["id"], "utterance_version": item["version"], "representation": "candidate", "candidate_id": value["id"], "candidate_version": value["version"], "text": "我理解的是，你不能接受目前的安排，并不会参加。"}
    response = post(client, f"/topics/{topic['id']}/understandings", body, key)
    assert response.status_code == 200
    return response.json(), body


def enabled_adapter(monkeypatch, handler):
    monkeypatch.setenv("SYMSOIL_AI_ENABLED", "true")
    monkeypatch.setenv("SYMSOIL_OLLAMA_MODEL", "local-test:1b")
    monkeypatch.setenv("SYMSOIL_OLLAMA_URL", "http://127.0.0.1:11434")
    return OllamaAdapter(transport=httpx.MockTransport(handler))


def valid_completion():
    return {"message": {"role": "assistant", "content": json.dumps({"candidates": [{"kind": "everyday", "text": "我不能接受安排，也不参加。"}, {"kind": "discussion", "text": "本次讨论中我保留拒绝意见，并不承诺参与。"}], "clarifications": ["需要明确哪些安排？"]}, ensure_ascii=False)}, "done": True}


def protocol_handler(request):
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "local-test:1b"}]})
    assert request.url.path == "/api/chat"
    return httpx.Response(200, json=valid_completion())


def test_candidate_limits_privacy_and_unknown_origin(harness):
    _app, _ids, login = harness
    author, admin = login("qiao"), login("admin")
    item = original(author)
    candidate(author, item)
    candidate(author, item, "discussion", "讨论表达")
    duplicate = post(author, f"/utterances/{item['id']}/candidates", {"object_version": 1, "kind": "everyday", "text": "不能覆盖", "context": "", "target_context": "", "purpose": ""})
    assert duplicate.status_code == 409
    assert admin.get(f"/api/v1/utterances/{item['id']}/expression").status_code == 404
    assert post(admin, f"/utterances/{item['id']}/candidates", {"object_version": 1, "kind": "everyday", "text": "越权", "context": "", "target_context": "", "purpose": ""}).status_code == 404
    assert post(author, f"/utterances/{item['id']}/candidates", {"object_version": 1, "kind": "everyday", "text": "冒充", "context": "", "target_context": "", "purpose": "", "origin": "local_model"}).status_code == 422


def test_choice_confirms_candidate_separately_without_sharing(harness):
    _app, _ids, login = harness
    author = login("qiao")
    item, topic = original(author), discussion(author)
    value = candidate(author, item)
    chosen = choose(author, item, value)
    assert chosen["choice"]["version"] == 1 and chosen["candidates"][0]["confirmed_version"] == 1
    assert chosen["utterance"]["confirmed_version"] is None and chosen["share"] is None
    assert author.get(f"/api/v1/topics/{topic['id']}").json()["viewpoints"] == []
    assert post(author, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": topic["id"], "representation": "candidate", "candidate_id": value["id"], "candidate_version": 1, "choice_version": 1}, "premature").status_code == 422


def test_candidate_sharing_never_exposes_original_context_or_other_candidate(harness):
    _app, _ids, login = harness
    author, observer = login("qiao"), login("lin")
    item, value, topic, _body = shared_candidate(author)
    candidate(author, item, "discussion", "另一私人候选")
    response = observer.get(f"/api/v1/topics/{topic['id']}")
    viewpoint = response.json()["viewpoints"][0]
    assert viewpoint["text"] == value["text"] and viewpoint["representation"] == "candidate"
    assert "私人原话：" not in response.text and "私人背景" not in response.text and "私人目标语境" not in response.text and "另一私人候选" not in response.text
    assert set(viewpoint) == {"id", "author_id", "author_name", "text", "utterance_version", "confirmed_at", "representation", "candidate_id", "candidate_version"}


def test_candidate_edit_invalidates_choice_share_and_confirmation(harness):
    _app, _ids, login = harness
    author = login("qiao")
    item, value, topic, body = shared_candidate(author)
    response = author.patch(f"/api/v1/utterances/{item['id']}/candidates/{value['id']}", json={"object_version": 1, "candidate_version": 1, "text": "改了一字。", "context": "", "target_context": "", "purpose": ""})
    assert response.status_code == 200
    detail = response.json()
    assert detail["choice"] is None and detail["share"] is None
    assert detail["candidates"][0]["version"] == 2 and detail["candidates"][0]["confirmed_version"] is None
    assert detail["utterance"]["confirmed_version"] == 1
    assert author.get(f"/api/v1/topics/{topic['id']}").json()["viewpoints"] == []
    # Old network replay returns its original outcome to the owner, not a new publication.
    assert post(author, f"/utterances/{item['id']}/share", body, "share-candidate").status_code == 200
    assert author.get(f"/api/v1/topics/{topic['id']}").json()["viewpoints"] == []


def test_original_edit_hides_old_candidates_and_resets_choice(harness):
    _app, _ids, login = harness
    author = login("qiao")
    item, value, topic, _body = shared_candidate(author)
    assert author.patch(f"/api/v1/utterances/{item['id']}", json={"object_version": 1, "title": "新原话", "text": "修改原话"}).status_code == 200
    detail = author.get(f"/api/v1/utterances/{item['id']}/expression").json()
    assert detail["candidates"] == [] and detail["choice"] is None and detail["share"] is None
    assert author.get(f"/api/v1/topics/{topic['id']}").json()["viewpoints"] == []
    assert author.patch(f"/api/v1/utterances/{item['id']}/candidates/{value['id']}", json={"object_version": 2, "candidate_version": 1, "text": "old", "context": "", "target_context": "", "purpose": ""}).status_code == 404


def test_choice_changes_clear_share_and_preserve_right_to_original(harness):
    _app, _ids, login = harness
    author = login("qiao")
    item, value, topic, _body = shared_candidate(author)
    response = post(author, f"/utterances/{item['id']}/choice", {"object_version": 1, "choice_version": 1, "choice": "no_rephrase"}, "decline-rephrase")
    assert response.status_code == 200 and response.json()["share"] is None
    assert author.get(f"/api/v1/topics/{topic['id']}").json()["viewpoints"] == []
    assert post(author, f"/utterances/{item['id']}/choice", {"object_version": 1, "choice_version": 0, "choice": "original_only"}, "stale-choice").status_code == 409
    shared = post(author, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": topic["id"]}, "share-original")
    assert shared.status_code == 200 and shared.json()["representation"] == "original" and shared.json()["text"] == item["text"]
    assert post(author, f"/utterances/{item['id']}/choice", {"object_version": 1, "choice_version": 2, "choice": "original_only", "candidate_id": value["id"]}, "malformed").status_code == 422


def test_understanding_bilateral_author_only_and_accuracy_is_not_stance(harness):
    _app, _ids, login = harness
    author, listener, admin = login("qiao"), login("lin"), login("admin")
    item, value, topic, _body = shared_candidate(author)
    record, body = comprehension(listener, item, value, topic)
    assert post(author, f"/topics/{topic['id']}/understandings", body, "self").status_code == 422
    assert len(author.get("/api/v1/understandings").json()) == len(listener.get("/api/v1/understandings").json()) == 1
    assert admin.get("/api/v1/understandings").json() == []
    response_body = {"object_version": 1, "status": "accurate", "correction": ""}
    assert post(listener, f"/understandings/{record['id']}/response", response_body).status_code == 404
    assert post(admin, f"/understandings/{record['id']}/response", response_body).status_code == 404
    first = post(author, f"/understandings/{record['id']}/response", response_body, "respond")
    replay = post(author, f"/understandings/{record['id']}/response", response_body, "respond")
    assert first.status_code == 200 and first.json() == replay.json() and first.json()["version"] == 2
    detail = listener.get(f"/api/v1/topics/{topic['id']}").json()
    assert "understandings" not in detail and all(not option["stances"] for option in detail["options"])


def test_understanding_correction_requires_text_and_source_revoke_blocks_replay(harness):
    _app, _ids, login = harness
    author, listener = login("qiao"), login("lin")
    item, value, topic, share_body = shared_candidate(author)
    record, request_body = comprehension(listener, item, value, topic)
    path = f"/understandings/{record['id']}/response"
    assert post(author, path, {"object_version": 1, "status": "needs_correction", "correction": " "}).status_code == 422
    response_body = {"object_version": 1, "status": "needs_correction", "correction": "我的拒绝针对这次安排，不是拒绝所有活动。"}
    assert post(author, path, response_body, "correction").status_code == 200
    post(author, f"/utterances/{item['id']}/revoke", {"object_version": 1})
    assert author.get("/api/v1/understandings").json() == listener.get("/api/v1/understandings").json() == []
    assert post(author, path, response_body, "correction").status_code == 404
    assert post(listener, f"/topics/{topic['id']}/understandings", request_body).status_code == 404
    # An explicit new share of exactly the same candidate/version restores access.
    assert post(author, f"/utterances/{item['id']}/share", share_body, "reshare-same").status_code == 200
    assert author.get("/api/v1/understandings").json()[0]["status"] == "needs_correction"


def test_understanding_representational_change_and_topic_cache_invalidated(harness):
    _app, _ids, login = harness
    author, listener = login("qiao"), login("lin")
    item, value, topic, _body = shared_candidate(author)
    comprehension(listener, item, value, topic)
    option = listener.get(f"/api/v1/topics/{topic['id']}").json()["options"][0]
    path, stance = f"/topics/{topic['id']}/stances", {"option_id": option["id"], "option_version": 1, "stance": "reservation"}
    assert post(listener, path, stance, "cached-topic").json()["viewpoints"]
    assert post(author, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": topic["id"]}, "share-original").status_code == 200
    assert listener.get("/api/v1/understandings").json() == []
    assert post(listener, path, stance, "cached-topic").json()["viewpoints"] == []


def test_existing_database_keeps_old_tables_columns_accounts_and_original_shares(harness):
    app, ids, login = harness
    author = login("qiao")
    item, topic = original(author), discussion(author)
    post(author, f"/utterances/{item['id']}/confirmations", {"object_version": 1}, "confirm")
    post(author, f"/utterances/{item['id']}/share", {"object_version": 1, "topic_id": topic["id"]}, "share")
    old_tables = {"users", "sessions", "registration_invites", "topics", "participants", "utterances", "options", "stances", "task_invitations", "documents", "audit_events", "idempotency_records"}
    before = {table: [column["name"] for column in inspect(app.state.engine).get_columns(table)] for table in old_tables}
    for model in (Understanding, ExpressionShare, ExpressionChoice, ExpressionCandidate):
        model.__table__.drop(app.state.engine)
    reopened = create_app(str(app.state.engine.url))
    after = {table: [column["name"] for column in inspect(reopened.state.engine).get_columns(table)] for table in old_tables}
    assert before == after
    with reopened.state.session_factory() as db:
        assert db.get(User, ids["qiao"]).username == "qiao"
    client = TestClient(reopened)
    response = client.post("/api/v1/auth/login", json={"username": "qiao", "password": "only-test-password-2026"})
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.get(f"/api/v1/topics/{topic['id']}").json()["viewpoints"][0]["representation"] == "original"


def test_ai_disabled_makes_no_network_and_manual_path_remains(harness, monkeypatch):
    app, _ids, login = harness
    monkeypatch.setenv("SYMSOIL_AI_ENABLED", "false")
    app.state.ollama = OllamaAdapter(transport=httpx.MockTransport(lambda _request: pytest.fail("disabled AI must not connect")))
    author = login("qiao")
    item = original(author)
    assert author.get("/api/v1/ai/status").json()["available"] is False
    response = post(author, f"/utterances/{item['id']}/suggestions", {"object_version": 1, "context": "", "target_context": "", "purpose": ""})
    assert response.status_code == 503
    assert candidate(author, item)["origin"] == "manual"


def test_model_protocol_only_explicit_source_context_no_tools_and_no_automatic_save(harness, monkeypatch):
    app, _ids, login = harness
    requests = []
    def handler(request):
        requests.append(request)
        return protocol_handler(request)
    app.state.ollama = enabled_adapter(monkeypatch, handler)
    author = login("qiao")
    item = original(author)
    fields = {"object_version": 1, "context": "本人语境", "target_context": "日常交流", "purpose": "澄清拒绝"}
    response = post(author, f"/utterances/{item['id']}/suggestions", fields)
    assert response.status_code == 200
    assert author.get(f"/api/v1/utterances/{item['id']}/expression").json()["candidates"] == []
    chat = json.loads(next(request.content for request in requests if request.url.path == "/api/chat"))
    assert chat["stream"] is False and "tools" not in chat
    assert chat["format"]["properties"]["candidates"]["maxItems"] == 2
    assert json.loads(chat["messages"][1]["content"]) == {"original": item["text"], "context": fields["context"], "target_context": fields["target_context"], "purpose": fields["purpose"]}
    assert response.json()["provider"] == "ollama"
    suggestion = response.json()["candidates"][0]
    assert "私人原话" not in base64.urlsafe_b64decode(suggestion["suggestion_token"].split(".")[0] + "==").decode()
    saved = post(author, f"/utterances/{item['id']}/candidates", {**fields, **suggestion})
    assert saved.status_code == 200 and saved.json()["candidates"][0]["origin"] == "local_model"


def test_model_suggestion_token_rejects_changed_content_actor_expiry_and_restart(harness, monkeypatch):
    app, ids, login = harness
    author = login("qiao")
    item = original(author)
    fields = {"object_version": 1, "kind": "everyday", "text": "待确认建议", "context": "", "target_context": "", "purpose": ""}
    token = app.state.suggestion_signer.issue(ids["qiao"], item["id"], 1, fields["kind"], fields["text"], "", "", "")
    path = f"/utterances/{item['id']}/candidates"
    assert post(author, path, {**fields, "text": "被修改", "suggestion_token": token}).status_code == 422
    foreign = app.state.suggestion_signer.issue(ids["lin"], item["id"], 1, fields["kind"], fields["text"], "", "", "")
    assert post(author, path, {**fields, "suggestion_token": foreign}).status_code == 422
    with pytest.raises(Exception) as restarted:
        SuggestionSigner().verify(token, ids["qiao"], item["id"], 1, fields["kind"], fields["text"], "", "", "")
    assert restarted.value.status_code == 422
    monkeypatch.setattr("symsoil_api.suggestion_tokens.time.time", lambda: time.time_ns() / 1e9 + 601)
    assert post(author, path, {**fields, "suggestion_token": token}).status_code == 422
    assert post(author, path, fields).status_code == 200  # Explicit manual fallback.


@pytest.mark.parametrize("url,model", [("https://127.0.0.1:11434", "local:1b"), ("http://localhost:11434", "local:1b"), ("http://169.254.169.254", "local:1b"), ("http://8.8.8.8", "local:1b"), ("http://user:secret@127.0.0.1:11434", "local:1b"), ("http://127.0.0.1:11434?secret=x", "local:1b"), ("http://127.0.0.1:11434", "model:cloud")])
def test_model_rejects_nonlocal_or_cloud_config_without_request(monkeypatch, url, model):
    monkeypatch.setenv("SYMSOIL_AI_ENABLED", "true")
    monkeypatch.setenv("SYMSOIL_OLLAMA_URL", url)
    monkeypatch.setenv("SYMSOIL_OLLAMA_MODEL", model)
    adapter = OllamaAdapter(transport=httpx.MockTransport(lambda _request: pytest.fail("unsafe config must not connect")))
    assert adapter.status()["available"] is False
    with pytest.raises(Exception) as error:
        adapter.suggestions("text", "", "", "")
    assert error.value.status_code == 503


@pytest.mark.parametrize("bad", ["malformed", {"candidates": [], "clarifications": []}, {"candidates": [{"kind": "everyday", "text": " "}], "clarifications": []}, {"candidates": [{"kind": "everyday", "text": "a"}, {"kind": "everyday", "text": "b"}], "clarifications": []}, {"candidates": [{"kind": "everyday", "text": "a"}], "clarifications": [], "unknown": "secret"}, {"candidates": [{"kind": "everyday", "text": "x" * 10001}], "clarifications": []}, {"candidates": [{"kind": "everyday", "text": "a"}, {"kind": "discussion", "text": "b"}, {"kind": "everyday", "text": "c"}], "clarifications": []}])
def test_model_malicious_output_does_not_save_or_confirm(harness, monkeypatch, bad):
    app, _ids, login = harness
    def handler(request):
        if request.url.path == "/api/tags":
            return protocol_handler(request)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": bad if isinstance(bad, str) else json.dumps(bad)}, "done": True})
    app.state.ollama = enabled_adapter(monkeypatch, handler)
    author = login("qiao")
    item = original(author)
    response = post(author, f"/utterances/{item['id']}/suggestions", {"object_version": 1, "context": "", "target_context": "", "purpose": ""})
    assert response.status_code == 503
    detail = author.get(f"/api/v1/utterances/{item['id']}/expression").json()
    assert detail["candidates"] == [] and detail["choice"] is None and detail["share"] is None


def test_model_missing_timeout_redirect_proxy_size_and_single_concurrency(harness, monkeypatch):
    app, _ids, login = harness
    monkeypatch.setenv("HTTP_PROXY", "http://attacker.invalid")
    adapter = enabled_adapter(monkeypatch, lambda _request: httpx.Response(200, json={"models": []}))
    assert adapter.status()["available"] is False
    with pytest.raises(Exception) as error:
        adapter.suggestions("text", "", "", "")
    assert error.value.status_code == 503
    # A fixed endpoint client bypasses proxy environment and does not follow redirects.
    with adapter.client() as client:
        assert client.follow_redirects is False and client._trust_env is False
    for handler in (lambda _request: httpx.Response(302, headers={"location": "https://attacker.invalid"}), lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("private text must not escape", request=request)), lambda _request: httpx.Response(200, content=b"x" * 256001)):
        adapter = enabled_adapter(monkeypatch, handler)
        with pytest.raises(Exception) as error:
            adapter.suggestions("text", "", "", "")
        assert error.value.status_code == 503 and "private text" not in error.value.detail
    adapter = enabled_adapter(monkeypatch, protocol_handler)
    adapter.gate.acquire()
    try:
        with pytest.raises(Exception) as error:
            adapter.suggestions("text", "", "", "")
        assert error.value.status_code == 429
    finally:
        adapter.gate.release()


def test_model_can_return_only_clarification_and_rejects_incomplete_completion(monkeypatch):
    def handler(request):
        if request.url.path == "/api/tags":
            return protocol_handler(request)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"candidates": [], "clarifications": ["哪些安排是你不能接受的？"]})}, "done": True})
    adapter = enabled_adapter(monkeypatch, handler)
    assert adapter.suggestions("我不接受", "", "", "")["candidates"] == []
    def incomplete(request):
        if request.url.path == "/api/tags":
            return protocol_handler(request)
        return httpx.Response(200, json={**valid_completion(), "done": False})
    adapter = enabled_adapter(monkeypatch, incomplete)
    with pytest.raises(Exception) as error:
        adapter.suggestions("text", "", "", "")
    assert error.value.status_code == 503


def test_model_overall_collection_deadline_cancels_slow_stream_and_releases_gate(monkeypatch):
    closed = []
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(20):
                await asyncio.sleep(0.02)
                yield b" "
        async def aclose(self):
            closed.append(True)
    async def handler(request):
        if request.url.path == "/api/tags":
            return protocol_handler(request)
        return httpx.Response(200, stream=SlowStream())
    adapter = enabled_adapter(monkeypatch, handler)
    adapter.total_timeout = 0.05
    start = time.monotonic()
    with pytest.raises(Exception) as error:
        adapter.suggestions("text", "", "", "")
    assert error.value.status_code == 503
    assert time.monotonic() - start < 0.2 and closed
    assert adapter.gate.acquire(blocking=False)
    adapter.gate.release()


def test_model_total_deadline_cancels_delayed_headers_and_probe(monkeypatch):
    async def handler(request):
        if request.url.path == "/api/tags":
            return protocol_handler(request)
        await asyncio.sleep(0.4)
        return httpx.Response(200, json=valid_completion())
    adapter = enabled_adapter(monkeypatch, handler)
    adapter.total_timeout = 0.04
    started = time.monotonic()
    with pytest.raises(Exception) as error:
        adapter.suggestions("text", "", "", "")
    assert error.value.status_code == 503 and time.monotonic() - started < 0.2
    async def delayed_probe(_request):
        await asyncio.sleep(0.4)
        return httpx.Response(200, json={"models": [{"name": "local-test:1b"}]})
    adapter = enabled_adapter(monkeypatch, delayed_probe)
    adapter.probe_timeout = 0.04
    started = time.monotonic()
    assert adapter.status()["available"] is False
    assert time.monotonic() - started < 0.2


@pytest.mark.parametrize("change,expected", [("freeze", 401), ("edit", 409)])
def test_model_call_releases_db_lock_and_rechecks_frozen_or_changed_source(harness, monkeypatch, change, expected):
    app, ids, login = harness
    author, admin, second = login("qiao"), login("admin"), login("qiao")
    item = original(author)
    started, release = Event(), Event()
    def handler(request):
        if request.url.path == "/api/tags":
            return protocol_handler(request)
        started.set()
        assert release.wait(5)
        return httpx.Response(200, json=valid_completion())
    app.state.ollama = enabled_adapter(monkeypatch, handler)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(post, author, f"/utterances/{item['id']}/suggestions", {"object_version": 1, "context": "", "target_context": "", "purpose": ""})
        assert started.wait(5)
        if change == "freeze":
            assert admin.post(f"/api/v1/admin/members/{ids['qiao']}/freeze").status_code == 200
        else:
            assert second.patch(f"/api/v1/utterances/{item['id']}", json={"object_version": 1, "title": "改写", "text": "新原话"}).status_code == 200
        release.set()
        assert future.result(timeout=5).status_code == expected
    with app.state.session_factory() as db:
        assert list(db.scalars(select(ExpressionCandidate))) == []
