# ChainScope X R7 Application Guide

## Pages

The authenticated application includes Dashboard (`/app`), New Analysis (`/app/analysis/new`), Analysis Runs (`/app/analysis-runs`), Run Details (`/app/analysis-runs/{run_id}`), Findings Explorer (`/app/findings`), Finding Details (`/app/findings/{finding_id}`), Execution Timeline (`/app/analysis-runs/{run_id}/timeline`), Evidence Explorer (`/app/analysis-runs/{run_id}/evidence`), Policy Library (`/app/policies`), Policy Details (`/app/policies/{document_id}`), System Health (`/app/system`), and Account & Access (`/app/account`). Google sign-in is at `/login` and uses the existing OIDC flow; no demo-login path exists.

## Run locally

Use Python 3.13.5 where available. From the repository root:

```sh
python3 -m venv /root/.venvs/chainscope-x-r7-py313
. /root/.venvs/chainscope-x-r7-py313/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip check
APP_ENV=development HOST=127.0.0.1 python -m pytest -q
APP_ENV=development HOST=127.0.0.1 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/login`. Use a separate isolated R7 checkout and virtual environment on the tablet; do not reuse earlier milestone environments.

## Frontend structure and API integration

The server-rendered interface uses FastAPI, Jinja2 templates in `frontend/templates`, the checked-in local HTMX runtime at `frontend/static/vendor/htmx.min.js`, local CSS in `frontend/static/css/app.css`, and vanilla JavaScript in `frontend/static/js/app.js`. It does not require a JavaScript toolchain, build step, or runtime CDN. The UI consumes the existing analysis-run, event, evidence, dependency-health, policy-index/deactivate, session, and logout APIs. R7 adds `GET /api/v1/dashboard/summary`, `GET /api/v1/findings`, `GET /api/v1/findings/{finding_id}`, `GET /api/v1/policies`, and `GET /api/v1/policies/{document_id}`. The added read APIs query the existing PostgreSQL repository and return bounded pagination; they do not fabricate data. The dashboard’s HTMX refresh fragment reads the same persisted summary.

Evidence screens show relational references separately from MongoDB evidence-document safe metadata. Raw evidence payloads are not rendered in the browser. Coverage is shown per run when stored; no aggregate score is invented.

## Authentication and RBAC

All `/app` pages require the existing authenticated identity. Google OIDC, PKCE, state/nonce checks, signed HttpOnly sessions, and CSRF remain in the R6 authentication layer. State-changing browser requests pass the CSRF token returned by `/auth/session`. Backend permissions remain authoritative: admins and analysts can run analyses and reconcile; viewers can read; only admins can index or deactivate policies. Hiding controls in the UI is not the security boundary.

## Configuration variable names

Configuration variable names (values belong only in local environment configuration): `APP_ENV`, `HOST`, `PORT`, `CHAIN_SCOPE_CHROMA_DIR`, `CHAIN_SCOPE_POLICY_DIR`, `FASTEMBED_CACHE_PATH`, `GROQ_MODEL_ID`, `CHAIN_SCOPE_POSTGRES_DSN`, `CHAIN_SCOPE_MONGODB_URI`, `CHAIN_SCOPE_MONGODB_DATABASE`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `CHAIN_SCOPE_SESSION_SECRET`, `CHAIN_SCOPE_ADMIN_GOOGLE_SUBJECTS`, `CHAIN_SCOPE_SESSION_MAX_AGE`, `CHAIN_SCOPE_SECURE_COOKIES`, `CHAIN_SCOPE_RATE_LIMIT_BACKEND`, `CHAIN_SCOPE_RATE_LIMIT_UNAUTHENTICATED`, `CHAIN_SCOPE_RATE_LIMIT_AUTHENTICATED`, `CHAIN_SCOPE_RATE_LIMIT_WINDOW_SECONDS`, and `CHAIN_SCOPE_TRUSTED_PROXY_CIDRS`. Not every variable is required for every local/test mode. See `.env.example` for default semantics. Never commit secret values or store them in browser storage.

## Local-only boundary and limitations

Business API endpoints remain restricted to development/test and loopback `HOST`. Do not expose the service to LAN or the public internet. `/health` is liveness only; `/api/v1/health/dependencies` checks dependencies separately. Live Google OAuth and live PostgreSQL/MongoDB integration are not claimed as verified here. The default in-memory rate limiter is local development/test only; shared production rate limiting, load balancing, object storage, and production deployment are not implemented. Chroma is reported as a local persistent store where available; a dependency health response is not proof that every policy retrieval workflow has been exercised.

## Verification commands

```sh
python -m pip check
python -m compileall -q .
python -m pytest -q
# The worktree must have no whitespace errors:
git diff --check
```
