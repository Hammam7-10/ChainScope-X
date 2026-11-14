# R6 Identity, Access Control, and Rate Limiting

R6 adds an authenticated protection layer around the existing local R5 API. R3 remains the only security-verdict authority, R2 remains the controlled execution boundary, and PostgreSQL, MongoDB, and ChromaDB retain their R5 responsibilities.

## Google OpenID Connect

The application uses Authlib's maintained Starlette integration and Google's OpenID Connect discovery document. The browser flow is authorization-code based and sends PKCE S256, a random state, and a random nonce. Authlib performs the authorization-code exchange and ID-token signature validation using the provider metadata and published keys. The application additionally enforces the expected issuer, audience, expiry handling from the library, subject, and `email_verified == true`.

Required variables are `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and `CHAIN_SCOPE_SESSION_SECRET`. The redirect URI must exactly match a URI configured in Google Cloud Console. Local development may use `http://127.0.0.1:8000/auth/google/callback`; deployed use requires HTTPS.

Missing Google credentials produce an explicit HTTP 503 configuration response. There is no simulated login and no development authentication bypass.

## Sessions and CSRF

Starlette's signed `SessionMiddleware` stores only the OAuth transaction fields, an opaque local user ID, identity display data, role snapshot, and a CSRF token. OAuth access and ID tokens are never stored in the session. The session cookie is HttpOnly, uses `SameSite=Lax`, has an eight-hour default maximum age, and is Secure when `CHAIN_SCOPE_SECURE_COOKIES=true` or when the application is outside development/test mode.

State-changing authenticated API operations require the `X-CSRF-Token` header matching the token returned by `GET /auth/session`. Logout also requires this header. OAuth state and nonce are single-use and expire after ten minutes.

## Users and role bootstrap

Migration `20261114_02` adds the PostgreSQL `users` table. The Google subject (`sub`) is the stable identity key. New users receive `viewer` by default. Only subjects explicitly listed in `CHAIN_SCOPE_ADMIN_GOOGLE_SUBJECTS` receive `admin` at first creation. Email addresses are never used as administrator bootstrap keys.

The permission matrix is:

| Permission | admin | analyst | viewer |
|---|---:|---:|---:|
| Run analyses | yes | yes | no |
| View runs/findings | yes | yes | yes |
| View evidence/events | yes | yes | yes |
| Modify/index policies | yes | no | no |
| Deactivate policies | yes | no | no |
| Trigger reconciliation | yes | yes | no |
| Administrative operations | yes | no | no |

All permissions are enforced by backend dependencies. Hiding a frontend control is not an authorization mechanism.

## Rate limiting

Authentication endpoints are limited by client IP. Authenticated API requests are limited by user ID. The response is HTTP 429 with a `Retry-After` header when the limit is exceeded.

The default `memory` backend is intentionally restricted to development/test and is process-local. It must not be described as distributed and is not safe behind multiple application instances. The code exposes a `RateLimitStore` contract and rejects `shared` mode until an atomic shared implementation is configured. A future Redis or database-backed implementation must use an atomic increment/expiry operation and must be selected explicitly with `CHAIN_SCOPE_RATE_LIMIT_BACKEND=shared`.

Forwarded client IPs are ignored unless the direct peer belongs to one of the explicitly configured `CHAIN_SCOPE_TRUSTED_PROXY_CIDRS` networks. Do not add arbitrary proxy networks.

## Protected routes and limitations

`/health` remains minimal. `/api/v1/health/dependencies` remains local-only and reports configuration state without credentials. R5 analysis, run, evidence, event, policy, and reconciliation routes require Google authentication, an active persisted user, the appropriate role, and CSRF for state changes.

R6 does not implement a dashboard, object storage, load balancer, shared rate-limit service, or production deployment. The application remains loopback-only unless a separately reviewed secure deployment mode is introduced. Tests use mocks and fixtures and do not require Google credentials or live databases.
