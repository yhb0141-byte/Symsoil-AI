# SymSoil API · R0

This service is a **synthetic-data development release**. It implements local accounts, restricted topics, private original expressions, distinct accuracy confirmation and explicit sharing, five stances, and independently accepted task invitations. It does not approve community decisions or execute projects. AI is explicitly unavailable; the manual paths remain usable.

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

## Boundary and transactions

Authentication tokens are random and stored only as SHA-256 hashes in server sessions. Passwords use Argon2id. Registration invitations are random, stored hashed, expire after seven days, and are consumed in the same transaction as user creation. The account directory exposes only member IDs and display names. Administrators manage accounts but have no global private draft privilege.

Authenticated POST/PATCH operations require `X-CSRF-Token`. Exact origin checks, same-site cookies, strict body fields, bounds, and no API CORS supplement that check. Errors contain strings rather than submitted field values. API responses are `no-store`. Session and audit endpoints never expose token hashes, CSRF secrets for other sessions, password hashes, or private bodies.

Expression `version` is the content revision. Editing creates the next version and clears confirmation and sharing. Confirmation does not share. Sharing in R0 explicitly publishes the confirmed original text to one topic; there is no generated reformulation. Revocation immediately removes it from current topic reads. R0 does not expose a revision-history interface or record withdrawn private text in audit entries.

Business writes use conditional SQL updates, not read-check-then-unconditional updates. Authenticated requests guard the active session in the write transaction. Required idempotency keys are actor and operation scoped; the normalized request hash, effect, audit event, and response are committed together. Retrying the same completed request returns its outcome; reusing a key for a different body returns 409. Object permissions are checked before replay. Current revocation takes precedence over stale text in a cached topic response.

Topics are accessible only to invited participants. Only an owner can add participants or issue task invitations. Task terms are visible only to issuer and recipient, even in topic details. An invitation can go to a member who cannot read the topic; accepting it does not grant topic access. A final acceptance/refusal ends that invitation; renegotiation remains open. No response means no stance and no task acceptance.

## Tests and release limits

```bash
.venv/bin/python -m pytest services/api/tests -q
```

The suite uses isolated file-backed SQLite, fresh synthetic users, distinct browser sessions, and temporary assets. It covers CSRF, ACL, version conflicts, withdrawal, five stances, idempotency, invitation boundaries, freezing, and one-use/expired registration invitations. A browser run and frontend build belong to the repository-wide verification.

R0 does not include MFA, account recovery, distributed rate limiting, real knowledge ingestion, model inference, public-screen sessions, approval, memory publication, data export/deletion workflows, backups, or production schema migration tooling. Tables are created for empty development databases. Existing schema changes require a reviewed migration before retaining any business data; do not treat `create_all` as a migration system. PostgreSQL driver compatibility is provided but its concurrent transaction behavior still needs integration testing before real use.
