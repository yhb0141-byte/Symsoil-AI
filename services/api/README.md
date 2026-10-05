# SymSoil API · R0.3

This service is a **synthetic-data development release**. It implements local accounts, restricted topics, private original expressions, two optional reformulations, independent accuracy confirmation and explicit sharing, private bilateral understanding checks, five stances, independently accepted task invitations, and an explicitly reviewed text knowledge library. It does not approve community decisions or execute projects. Local Ollama suggestions are optional and disabled by default; every manual path remains usable.

## Run

From the repository root, using Python 3.12 or later:

```bash
python -m venv .venv
.venv/bin/pip install -r services/api/requirements-dev.txt
.venv/bin/pip install --no-deps -e services/api
export DATABASE_URL=sqlite:///./data/symsoil.db
read -rs SYMSOIL_DEMO_PASSWORD
export SYMSOIL_DEMO_PASSWORD
.venv/bin/python -m symsoil_api.cli seed --demo
unset SYMSOIL_DEMO_PASSWORD
.venv/bin/uvicorn symsoil_api.main:app --host 127.0.0.1 --port 8000
```

Enter an explicit demo password of 12–128 characters before running the seed. Accounts `admin`, `lin`, and `qiao` share that **demo-only** password; seed refuses an existing account database and never resets credentials. No default password, model download, remote API call, CDN, or telemetry is included. Do not use the demo credential arrangement for real members.

After the frontend has been built, its `apps/web/dist` is served by FastAPI at the same origin. Set `SYMSOIL_WEB_DIST` to an alternative absolute directory **before startup**. Unknown `/api/*` and missing static assets return 404 instead of SPA HTML. Without a built frontend, only the API is served.

## Configuration

| Variable | Development default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/symsoil.db` | Local SQLite. `postgresql+psycopg://…` also supported by SQLAlchemy; PostgreSQL deployment is not yet integration tested. |
| `SYMSOIL_COOKIE_SECURE` | `false` | Local HTTP only. Set `true` for HTTPS. Cookies are always HttpOnly, SameSite=Strict, and server-revocable. |
| `SYMSOIL_MODE` | `development` | `production` refuses startup unless secure cookies are enabled. R0 is still unsuitable for real-data production regardless of this setting. |
| `SYMSOIL_ALLOWED_ORIGINS` | request's exact origin | Comma-separated exact allowed origins, e.g. `http://localhost:5173,http://127.0.0.1:5173` for Vite. This does not enable CORS. |
| `SYMSOIL_SESSION_IDLE_MINUTES` | `5` | Server idle expiry; total session lifetime remains eight hours. Frontend terminal logout supplements this rule. |
| `SYMSOIL_WEB_DIST` | root `apps/web/dist` | Built SPA directory; no external assets fetched. |
| `SYMSOIL_DEMO_PASSWORD` | none | Explicit temporary seed input. Never put it in tracked files. |
| `SYMSOIL_AI_ENABLED` | `false` | Enable only private local model previews. |
| `SYMSOIL_OLLAMA_MODEL` | none | Exact installed local model tag. Cloud names and models reported as remote are rejected. |
| `SYMSOIL_OLLAMA_URL` | `http://127.0.0.1:11434` | HTTP with a literal loopback IP only; no DNS, URL credentials, query, fragment, redirects, or environment proxy. |

## Boundary and transactions

Authentication tokens are random and stored only as SHA-256 hashes in server sessions. Passwords use Argon2id. Registration invitations are random, stored hashed, expire after seven days, and are consumed in the same transaction as user creation. The account directory exposes only member IDs and display names. Administrators manage accounts but have no global private draft privilege.

All authenticated requests, including GET, require `X-CSRF-Token` in addition to the HttpOnly cookie. Only explicit login returns the proof; a cookie alone cannot bootstrap a private read or recover the proof after an offline logout. Exact origin checks on mutations, same-site cookies, strict body fields, bounds, and no API CORS supplement that check. Errors contain strings rather than submitted field values. API responses are `no-store`. Session and audit endpoints never expose token hashes, CSRF secrets for other sessions, password hashes, or private bodies.

Expression `version` is the original content revision. Editing creates the next version and clears its confirmation, current choice, and sharing. A member can keep one `everyday` and one `discussion` candidate for the current version, including explicitly supplied private context. Selecting a specific candidate version confirms that reformulation; it does not confirm the original or share anything. Sharing either original or reformulation always requires a separately confirmed original; sharing a reformulation additionally checks the exact current choice and candidate version. A topic receives only the one explicitly shared body, never the private original/context alongside a reformulation. Changing a confirmed candidate or choice stops the current publication; revocation or original editing immediately removes it from current topic reads. No private text is copied into audit entries.

Understanding checks are listener-authored paraphrases of a currently shared viewpoint. Only that listener and the expression's author can read them; only the author can respond. A withdrawn, rewritten, or differently represented source makes them inaccessible, including before cached replay. Explicitly sharing the identical source version again can restore access to the existing check. An `accurate` response changes only the private understanding record, never stances, task acceptance, or approval.

R0.2 adds four tables without altering existing columns. Existing synthetic users, documents, and original shares are retained; original shares without new metadata continue to mean original text. Old original-share idempotency hashes remain compatible. Candidate/choice historical versions are not exposed as a revision-history interface; this is still not a production migration system.

Business writes use conditional SQL updates, not read-check-then-unconditional updates. Authenticated requests guard the active session in the write transaction. Required idempotency keys are actor and operation scoped; the normalized request hash, effect, audit event, and response are committed together. Retrying the same completed request returns its outcome; reusing a key for a different body returns 409. Object permissions are checked before replay. Current revocation takes precedence over stale text in a cached topic response.

Topics are accessible only to invited participants. Only an owner can add participants or issue task invitations. Task terms are visible only to issuer and recipient, even in topic details. An invitation can go to a member who cannot read the topic; accepting it does not grant topic access. A final acceptance/refusal ends that invitation; renegotiation remains open. No response means no stance and no task acceptance.

## Reviewed text library

R0.3 adds `knowledge_documents`, immutable `knowledge_revisions`, current `knowledge_audiences`, and `knowledge_reviews` without changing old columns. A private draft never creates or overwrites a legacy `documents` snapshot. Approval of an exact submitted revision publishes its snapshot and explicit audience in one transaction. A new private revision leaves the previous authorized publication accessible until separately approved. Submission reveals only that exact revision to one other currently active facilitator/admin; it gives no access to other drafts and no authority to approve decisions described by the document.

`GET /knowledge/mine` and `/knowledge/{id}` are author-only management views. The reviewer receives only the submitted revision through `/knowledge/reviews`; even an administrator cannot browse unsubmitted drafts. The author's `publication_active` and `audience` report server-evaluated current publication and effective ACL; `published` retains the last published revision as private history after expiry or withdrawal. Revision `requested_member_ids` records the immutable original request, not later restrictions.

Every directory result, dashboard document count, full-text read, quotation, and model context passes the same current-publication ACL. `community` means currently authenticated active members; `members` means an explicit fixed list plus the owner. Previous reviewers receive no continuing directory privilege. Expired, withdrawn, missing-metadata, or old-revision publications return 404 and leave no title, snippet, count, or citation in current results. Literal keyword search escapes SQL LIKE metacharacters. Source text is never fetched or turned into an external download link.

The owner can cancel submission, withdraw a publication, or reduce an audience. Withdrawal and restriction also cancel pending review, preventing a previously submitted broad draft from republishing after withdrawal or restriction. Broadening or republishing needs a newly saved complete revision and independent review. A previously approved content revision cannot be submitted or approved again to restore its original broader audience. Author idempotent retries return the **current** management view; review retries return a minimal no-body receipt and never rerun publication. Text that someone already read or copied cannot be erased from their memory or copies.

New demo seed builds explicit metadata for the three original synthetic documents. A database upgraded from R0/R0.2 gets new tables only and **does not automatically approve old text**. To initialize only exact, unmodified original synthetic seed records, deliberately run:

```bash
.venv/bin/python -m symsoil_api.cli migrate-synthetic-documents --demo
```

This requires the known original synthetic account identities and exact title/category/body/source/version matches. It does not reset accounts, overwrite content, assign real-data owners, or approve unknown legacy records. Unknown old `Document` rows remain physically preserved and quarantined. For real-data migration, a reviewed ownership, licensing, audience, expiry, and recovery procedure is still required; `create_all` is not that procedure.

Only pasted ordinary text or a frontend local UTF-8 txt/md read is accepted, with strict bounds, metadata, timezone-aware optional expiry, and explicit member IDs. NUL, binary control characters, and surrogate codepoints are rejected. Binary upload, OCR, HTML rendering, embeddings, semantic search, and revision-history publication are outside this release.

`POST /knowledge/answers` uses simple Chinese bigrams and English words to rank at most five current authorized documents, with at most three real-line excerpts per document. The manual path explicitly says “资料摘录，非模型回答” and returns at most six server-generated citations. No matching sources returns `insufficient` without invoking a model. This is a small development catalogue, not validated semantic retrieval or a source of live task/decision truth. Full-text links must include current `revision_id`; replaced citations stop resolving.

Optional `use_model:true` calls the same local-only Ollama adapter and single inference gate as expression suggestions. It sends only the question and authorized `{citation_id,title,source,quote}` fragments. The output schema is `{answer,citation_ids}`; up to six distinct IDs must belong to this request, and a nonempty answer requires valid citations. The server reconstructs every title, quote, coordinate, version, and access epoch; model-created IDs, source-URL fields, extra metadata, tools, duplicate IDs, missing citations, and excessive outputs fail closed. No generated answer/question/context is written to the database or prompt logs. Model HTTP runs without the database writer lock and within the same cancellable 60-second total deadline.

Before returning either success or generation failure, the server reauthenticates the session and account and rechecks **every source sent**, including unreferenced candidate sources, against current publication, epoch, effective time, and ACL. Any source change returns 409; a frozen account returns 401. Private revision editing alone leaves unchanged current publications usable.

## Tests and release limits

```bash
.venv/bin/python -m pytest services/api/tests -q
```

The suite uses isolated file-backed SQLite, fresh synthetic users, distinct browser sessions, and temporary assets. It covers CSRF, ACL, version conflicts, withdrawal, five stances, idempotency, invitation boundaries, freezing, and one-use/expired registration invitations. A browser run and frontend build belong to the repository-wide verification.

## Optional local suggestions

Install Ollama and the chosen model as a separate, explicit maintenance action. Configure `OLLAMA_NO_CLOUD=1` on the **actual Ollama daemon** and restart it; an environment variable on FastAPI alone cannot disable daemon cloud forwarding. Verify the daemon's local-only setting and external-network restrictions. The application never calls `/api/pull`, never downloads models, and never falls back to cloud providers.

`GET /api/v1/ai/status` checks local `/api/tags`; an enabled configuration alone does not mean an installed model exists. A suggestion request sends only the current private original and three contexts explicitly supplied for that request. It uses `/api/chat` with `stream:false`, a strict output schema, no tools, a three-second total tags probe, a cancellable 60-second total HTTP operation, bounded response bytes, and one inference request per process. `httpx.AsyncClient` with `asyncio.timeout` cancels delayed headers or slow streams at the overall deadline; socket read timeouts provide an additional bound. Model failure returns a safe 503; a busy local inference returns 429. Output is validated again and may contain up to two different candidate kinds or only clarification questions. It is never automatically saved, confirmed, or shared.

The database write transaction is released during model I/O. Before returning a preview, the service checks the session proof, active account, author, and original version again. An account frozen during generation gets 401; a changed original gets 409. Failed generation also runs this current-permission check. Private prompt/model bodies are not logged.

Each unsaved candidate preview has a ten-minute HMAC provenance token. The token contains actor/source/version/kind, the digest of all candidate fields, and expiry; it contains no private body. Saving the unchanged suggestion with its valid token records `origin=local_model`. Editing any field, omitting the token, or patching a saved candidate records `manual`. Altered/foreign/expired tokens are rejected; a server restart invalidates unsaved preview tokens. The member can explicitly save their text without a proof as manual. Model provenance establishes source, not meaning accuracy; the member still confirms their own expression.

Official protocol references: [Chat API](https://docs.ollama.com/api/chat), [structured output](https://docs.ollama.com/capabilities/structured-outputs), [local-only configuration](https://docs.ollama.com/faq).

R0.3 does not include MFA, account recovery, distributed rate limiting, binary knowledge ingestion, semantic/vector search, validated real-model answer quality, public-screen sessions, formal decision approval, memory publication, data export/deletion workflows, backups, or production migration/recovery tooling. A real installed model was not used in the automated protocol tests; they inject a mock HTTP transport and do not validate semantic quality. Existing schema changes require a reviewed migration before retaining any business data; do not treat `create_all` as a migration system. PostgreSQL driver compatibility is provided but its concurrent transaction behavior still needs integration testing before real use.

## R0.4 双方资料纠错

接口合同：`docs/development/API_CONTRACT_R04.md`。新增 `knowledge_corrections` 表和 `/documents/{id}/correction-context`、`/knowledge-corrections` 列表／创建／详情、`/{id}/respond` 与 `/{id}/withdraw`。继续使用会话 Cookie、CSRF、对象版本和 Idempotency-Key。请求只保存显式问题与回应及关联身份，不保存原文或标题快照。来源动态按当前精确发布版与受众鉴权，不能把纠错正文进入检索。管理员身份不扩大双方读取范围。
