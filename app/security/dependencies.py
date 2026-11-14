from __future__ import annotations

import ipaddress
import os
from typing import Callable

from fastapi import Depends, HTTPException, Request

from app.database.config import DatabaseConfig, DatabaseConfigurationError
from app.database.mongo import MongoDocumentStore
from app.database.postgres import PostgresRepository
from app.persistence.service import R5PersistenceService
from app.security.auth import AuthenticatedIdentity, require_csrf, session_identity
from app.security.config import SecurityConfig, SecurityConfigurationError
from app.security.rate_limit import InMemoryRateLimitStore, RateLimiter, client_ip
from app.security.rbac import has_permission


def require_local_development(request: Request) -> None:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    bind_host = os.getenv("HOST", "127.0.0.1").strip().lower()
    client_host = request.client.host if request.client else ""
    try:
        client = ipaddress.ip_address(client_host)
        loopback = client.is_loopback or bool(getattr(client, "ipv4_mapped", None) and client.ipv4_mapped.is_loopback)
    except ValueError:
        loopback = app_env == "test" and client_host == "testclient"
    if app_env not in {"development", "dev", "test"} or bind_host not in {"127.0.0.1", "localhost", "::1"} or not loopback:
        raise HTTPException(status_code=503, detail={
            "code": "local_development_only",
            "message": "R5/R6 API endpoints are available only in local development; configure a secure deployment before network exposure.",
        })


def security_config() -> SecurityConfig:
    try:
        return SecurityConfig.from_environment()
    except SecurityConfigurationError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "authentication_not_configured",
            "message": str(exc),
        }) from None


def get_rate_limiter(request: Request, config: SecurityConfig) -> RateLimiter:
    limiter = getattr(request.app.state, "r6_rate_limiter", None)
    if limiter is not None:
        return limiter
    if config.rate_limit_backend == "shared":
        raise HTTPException(status_code=503, detail={
            "code": "shared_rate_limit_backend_not_configured",
            "message": "A shared rate-limit backend must be configured before deployment.",
        })
    limiter = RateLimiter(InMemoryRateLimitStore())
    request.app.state.r6_rate_limiter = limiter
    return limiter


async def get_r5_service(request: Request) -> R5PersistenceService:
    service = getattr(request.app.state, "r5_persistence_service", None)
    if service is not None:
        return service
    try:
        config = DatabaseConfig.from_environment()
    except DatabaseConfigurationError:
        raise HTTPException(status_code=503, detail={
            "code": "database_configuration_missing",
            "message": "PostgreSQL and MongoDB must be configured for authenticated R5 operations.",
        }) from None
    service = R5PersistenceService(
        PostgresRepository(config.postgres_dsn), MongoDocumentStore(config.mongodb_uri, config.mongodb_database)
    )
    request.app.state.r5_persistence_service = service
    return service


async def authenticated_identity(request: Request) -> AuthenticatedIdentity:
    require_local_development(request)
    identity = session_identity(request)
    if identity is None:
        raise HTTPException(status_code=401, detail={"code": "authentication_required", "message": "Sign in with Google is required."})
    service = await get_r5_service(request)
    user = await service.postgres.get_user(identity.user_id)
    if user is None or not user["active"]:
        request.session.clear()
        raise HTTPException(status_code=401, detail={"code": "session_invalid", "message": "The session is no longer valid."})
    refreshed = AuthenticatedIdentity(
        user_id=user["user_id"], google_subject=user["google_subject"], email=user["email"],
        name=user["name"], role=user["role"], csrf_token=identity.csrf_token,
    )
    request.session["identity"]["role"] = refreshed.role
    return refreshed


def protected(permission: str, *, state_changing: bool = False) -> Callable:
    async def dependency(
        request: Request,
        identity: AuthenticatedIdentity = Depends(authenticated_identity),
    ) -> AuthenticatedIdentity:
        config = security_config()
        limiter = get_rate_limiter(request, config)
        await limiter.enforce(
            request,
            key="user:" + identity.user_id,
            limit=config.authenticated_limit,
            window_seconds=config.rate_limit_window_seconds,
        )
        if not has_permission(identity.role, permission):
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "The account lacks this permission."})
        if state_changing:
            require_csrf(request)
        return identity
    return dependency


async def unauthenticated_rate_limit(request: Request) -> None:
    require_local_development(request)
    config = security_config()
    limiter = get_rate_limiter(request, config)
    await limiter.enforce(
        request,
        key="ip:" + client_ip(request, config.trusted_proxy_networks),
        limit=config.unauthenticated_limit,
        window_seconds=config.rate_limit_window_seconds,
    )
