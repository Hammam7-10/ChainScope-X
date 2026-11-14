from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_network
from typing import FrozenSet


class SecurityConfigurationError(RuntimeError):
    """Raised when security settings are absent or unsafe."""


@dataclass(frozen=True)
class SecurityConfig:
    app_env: str
    session_secret: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    secure_cookies: bool
    session_max_age: int
    admin_subjects: FrozenSet[str]
    rate_limit_backend: str
    unauthenticated_limit: int
    authenticated_limit: int
    rate_limit_window_seconds: int
    trusted_proxy_networks: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "SecurityConfig":
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        session_secret = os.getenv("CHAIN_SCOPE_SESSION_SECRET", "").strip()
        if not session_secret or len(session_secret) < 32:
            raise SecurityConfigurationError(
                "CHAIN_SCOPE_SESSION_SECRET must be set to at least 32 characters"
            )
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
        if not client_id or not client_secret or not redirect_uri:
            raise SecurityConfigurationError(
                "Google authentication requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
                "and GOOGLE_REDIRECT_URI"
            )
        if not redirect_uri.startswith("https://") and not (
            app_env in {"development", "dev", "test"}
            and redirect_uri.startswith("http://127.0.0.1")
        ):
            raise SecurityConfigurationError("GOOGLE_REDIRECT_URI must use HTTPS outside local development")
        backend = os.getenv("CHAIN_SCOPE_RATE_LIMIT_BACKEND", "memory").strip().lower()
        if backend not in {"memory", "shared"}:
            raise SecurityConfigurationError("CHAIN_SCOPE_RATE_LIMIT_BACKEND must be memory or shared")
        if backend == "memory" and app_env not in {"development", "dev", "test"}:
            raise SecurityConfigurationError(
                "The process-local memory rate limiter is permitted only in development/test; "
                "configure a shared backend for deployment"
            )
        try:
            networks = tuple(
                str(ip_network(item.strip(), strict=False))
                for item in os.getenv("CHAIN_SCOPE_TRUSTED_PROXY_CIDRS", "").split(",")
                if item.strip()
            )
            for item in networks:
                ip_network(item)
            unauth_limit = int(os.getenv("CHAIN_SCOPE_RATE_LIMIT_UNAUTHENTICATED", "20"))
            auth_limit = int(os.getenv("CHAIN_SCOPE_RATE_LIMIT_AUTHENTICATED", "120"))
            window = int(os.getenv("CHAIN_SCOPE_RATE_LIMIT_WINDOW_SECONDS", "60"))
        except ValueError as exc:
            raise SecurityConfigurationError("Invalid rate-limit or trusted-proxy configuration") from exc
        if min(unauth_limit, auth_limit, window) <= 0:
            raise SecurityConfigurationError("Rate-limit values must be positive")
        subjects = frozenset(
            item.strip() for item in os.getenv("CHAIN_SCOPE_ADMIN_GOOGLE_SUBJECTS", "").split(",") if item.strip()
        )
        return cls(
            app_env=app_env,
            session_secret=session_secret,
            google_client_id=client_id,
            google_client_secret=client_secret,
            google_redirect_uri=redirect_uri,
            secure_cookies=(
                os.getenv("CHAIN_SCOPE_SECURE_COOKIES", "").strip().lower() in {"1", "true", "yes"}
                if os.getenv("CHAIN_SCOPE_SECURE_COOKIES", "").strip()
                else app_env not in {"development", "dev", "test"}
            ),
            session_max_age=int(os.getenv("CHAIN_SCOPE_SESSION_MAX_AGE", "28800")),
            admin_subjects=subjects,
            rate_limit_backend=backend,
            unauthenticated_limit=unauth_limit,
            authenticated_limit=auth_limit,
            rate_limit_window_seconds=window,
            trusted_proxy_networks=networks,
        )
