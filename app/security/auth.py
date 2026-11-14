from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request

from app.security.config import SecurityConfig


@dataclass(frozen=True)
class AuthenticatedIdentity:
    user_id: str
    google_subject: str
    email: str
    name: str
    role: str
    csrf_token: str


class GoogleOIDC:
    def __init__(self, config: SecurityConfig) -> None:
        self.config = config
        self.oauth = OAuth()
        self.oauth.register(
            name="google",
            client_id=config.google_client_id,
            client_secret=config.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    async def begin(self, request: Request):
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = hashlib.sha256(verifier.encode("ascii")).digest()
        import base64
        code_challenge = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")
        request.session["oauth_state"] = state
        request.session["oauth_nonce"] = nonce
        request.session["oauth_verifier"] = verifier
        request.session["oauth_started_at"] = int(time.time())
        return await self.oauth.google.authorize_redirect(
            request,
            self.config.google_redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

    async def callback(self, request: Request) -> dict[str, Any]:
        expected_state = request.session.pop("oauth_state", None)
        nonce = request.session.pop("oauth_nonce", None)
        verifier = request.session.pop("oauth_verifier", None)
        started_at = int(request.session.pop("oauth_started_at", 0) or 0)
        supplied_state = request.query_params.get("state", "")
        if not expected_state or not hmac.compare_digest(expected_state, supplied_state):
            raise HTTPException(status_code=400, detail={"code": "oauth_state_invalid", "message": "OAuth state validation failed."})
        if not nonce or not verifier or not started_at or time.time() - started_at > 600:
            raise HTTPException(status_code=400, detail={"code": "oauth_transaction_expired", "message": "OAuth transaction expired."})
        try:
            token = await self.oauth.google.authorize_access_token(request, code_verifier=verifier)
            claims = self.oauth.google.parse_id_token(token, nonce=nonce)
        except Exception as exc:
            raise HTTPException(status_code=401, detail={"code": "oauth_token_invalid", "message": "Google identity validation failed."}) from exc
        if not isinstance(claims, dict):
            raise HTTPException(status_code=401, detail={"code": "oauth_claims_invalid", "message": "Google identity claims are invalid."})
        issuer = claims.get("iss")
        if issuer not in {"https://accounts.google.com", "accounts.google.com"}:
            raise HTTPException(status_code=401, detail={"code": "oauth_issuer_invalid", "message": "Google issuer is invalid."})
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self.config.google_client_id not in audiences:
            raise HTTPException(status_code=401, detail={"code": "oauth_audience_invalid", "message": "Google audience is invalid."})
        if not claims.get("email_verified") is True:
            raise HTTPException(status_code=403, detail={"code": "email_not_verified", "message": "A verified Google email is required."})
        if not claims.get("sub") or not claims.get("email"):
            raise HTTPException(status_code=401, detail={"code": "oauth_identity_incomplete", "message": "Google identity is incomplete."})
        return claims


def session_identity(request: Request) -> AuthenticatedIdentity | None:
    data = request.session.get("identity")
    csrf_token = request.session.get("csrf_token")
    if not isinstance(data, dict) or not csrf_token:
        return None
    required = {"user_id", "google_subject", "email", "name", "role"}
    if not required.issubset(data):
        return None
    return AuthenticatedIdentity(
        user_id=str(data["user_id"]), google_subject=str(data["google_subject"]),
        email=str(data["email"]), name=str(data["name"]), role=str(data["role"]),
        csrf_token=str(csrf_token),
    )


def require_csrf(request: Request) -> None:
    identity = session_identity(request)
    supplied = request.headers.get("x-csrf-token", "")
    if identity is None or not supplied or not hmac.compare_digest(identity.csrf_token, supplied):
        raise HTTPException(status_code=403, detail={"code": "csrf_invalid", "message": "CSRF validation failed."})
