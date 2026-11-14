from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.security.auth import GoogleOIDC, require_csrf, session_identity
from app.security.config import SecurityConfigurationError, SecurityConfig
from app.security.dependencies import security_config
from app.security.rate_limit import InMemoryRateLimitStore, RateLimiter, client_ip
from app.security.rbac import Role, has_permission


def make_request(*, client=("127.0.0.1", 5000), headers=None, query=b"") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": query, "client": client, "server": ("127.0.0.1", 8000),
        "root_path": "", "scheme": "http", "app": SimpleNamespace(),
    })


def config() -> SecurityConfig:
    return SecurityConfig(
        app_env="test", session_secret="s" * 32, google_client_id="client",
        google_client_secret="secret", google_redirect_uri="http://127.0.0.1:8000/auth/google/callback",
        secure_cookies=False, session_max_age=300, admin_subjects=frozenset({"admin-sub"}),
        rate_limit_backend="memory", unauthenticated_limit=2, authenticated_limit=4,
        rate_limit_window_seconds=60, trusted_proxy_networks=("127.0.0.0/8",),
    )


def test_missing_google_configuration_is_explicit(monkeypatch):
    for name in ("CHAIN_SCOPE_SESSION_SECRET", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(HTTPException) as error:
        security_config()
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "authentication_not_configured"


def test_role_permission_matrix_is_enforced():
    assert has_permission(Role.ADMIN, "admin.manage")
    assert has_permission(Role.ADMIN, "policy.modify")
    assert has_permission(Role.ANALYST, "analysis.run")
    assert has_permission(Role.ANALYST, "persistence.reconcile")
    assert not has_permission(Role.ANALYST, "policy.modify")
    assert has_permission(Role.VIEWER, "analysis.view")
    assert not has_permission(Role.VIEWER, "analysis.run")
    assert not has_permission(Role.VIEWER, "persistence.reconcile")


def test_rate_limiter_returns_retry_after_and_enforces_limit():
    async def scenario():
        limiter = RateLimiter(InMemoryRateLimitStore())
        request = make_request()
        await limiter.enforce(request, key="ip:127.0.0.1", limit=1, window_seconds=60)
        with pytest.raises(HTTPException) as error:
            await limiter.enforce(request, key="ip:127.0.0.1", limit=1, window_seconds=60)
        assert error.value.status_code == 429
        assert int(error.value.headers["Retry-After"]) > 0
    asyncio.run(scenario())


def test_forwarded_ip_is_used_only_from_trusted_proxy():
    direct = make_request(client=("192.0.2.10", 5000), headers={"x-forwarded-for": "198.51.100.2"})
    assert client_ip(direct, ()) == "192.0.2.10"
    trusted = make_request(client=("127.0.0.1", 5000), headers={"x-forwarded-for": "198.51.100.2, 127.0.0.1"})
    assert client_ip(trusted, ("127.0.0.0/8",)) == "198.51.100.2"


def test_csrf_requires_session_token():
    request = SimpleNamespace(headers={"x-csrf-token": "wrong"}, session={
        "identity": {"user_id": "u", "google_subject": "s", "email": "a@example.com", "name": "A", "role": "viewer"},
        "csrf_token": "expected",
    })
    assert session_identity(request) is not None
    with pytest.raises(HTTPException) as error:
        require_csrf(request)
    assert error.value.status_code == 403


class FakeOAuth:
    def __init__(self, claims):
        self.google = self
        self.claims = claims

    async def authorize_access_token(self, request, **kwargs):
        return {"id_token": "signed"}

    def parse_id_token(self, token, nonce):
        return self.claims


def oauth_request(state="state"):
    return SimpleNamespace(
        query_params={"state": state},
        session={"oauth_state": "state", "oauth_nonce": "nonce", "oauth_verifier": "verifier", "oauth_started_at": 9999999999},
    )


def test_oauth_state_failure_is_rejected_before_token_exchange():
    oidc = GoogleOIDC(config())
    request = oauth_request("wrong")
    with pytest.raises(HTTPException) as error:
        asyncio.run(oidc.callback(request))
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "oauth_state_invalid"


def test_oauth_requires_verified_email_and_expected_claims():
    oidc = GoogleOIDC(config())
    oidc.oauth = FakeOAuth({
        "iss": "https://accounts.google.com", "aud": "client", "sub": "subject",
        "email": "user@example.com", "email_verified": False,
    })
    with pytest.raises(HTTPException) as error:
        asyncio.run(oidc.callback(oauth_request()))
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "email_not_verified"


def test_oauth_accepts_only_expected_issuer_and_audience():
    oidc = GoogleOIDC(config())
    oidc.oauth = FakeOAuth({
        "iss": "https://attacker.example", "aud": "client", "sub": "subject",
        "email": "user@example.com", "email_verified": True,
    })
    with pytest.raises(HTTPException) as error:
        asyncio.run(oidc.callback(oauth_request()))
    assert error.value.detail["code"] == "oauth_issuer_invalid"
