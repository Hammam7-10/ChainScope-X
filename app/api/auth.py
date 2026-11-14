from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.v1 import get_service
from app.security.auth import GoogleOIDC, require_csrf
from app.security.dependencies import (
    authenticated_identity,
    get_rate_limiter,
    require_local_development,
    security_config,
    unauthenticated_rate_limit,
)

router = APIRouter(prefix="/auth", tags=["R6 authentication"])


@router.get("/google/start", dependencies=[Depends(unauthenticated_rate_limit)])
async def google_start(request: Request):
    config = security_config()
    return await GoogleOIDC(config).begin(request)


@router.get("/google/callback")
async def google_callback(request: Request):
    require_local_development(request)
    config = security_config()
    limiter = get_rate_limiter(request, config)
    from app.security.rate_limit import client_ip
    await limiter.enforce(
        request, key="ip:" + client_ip(request, config.trusted_proxy_networks),
        limit=config.unauthenticated_limit, window_seconds=config.rate_limit_window_seconds,
    )
    claims = await GoogleOIDC(config).callback(request)
    service = await get_service(request)
    user = await service.postgres.get_or_create_user(
        google_subject=str(claims["sub"]), email=str(claims["email"]),
        display_name=str(claims.get("name") or claims["email"]), admin_subjects=config.admin_subjects,
    )
    csrf_token = secrets.token_urlsafe(32)
    request.session.clear()
    request.session["identity"] = {
        "user_id": user["user_id"], "google_subject": user["google_subject"],
        "email": user["email"], "name": user["name"], "role": user["role"],
    }
    request.session["csrf_token"] = csrf_token
    return JSONResponse({
        "status": "authenticated", "user": {"user_id": user["user_id"], "email": user["email"],
        "name": user["name"], "role": user["role"]}, "csrf_token": csrf_token,
    })


@router.get("/session")
async def current_session(identity=Depends(authenticated_identity)):
    return {"authenticated": True, "user": {
        "user_id": identity.user_id, "email": identity.email, "name": identity.name,
        "role": identity.role,
    }, "csrf_token": identity.csrf_token}


@router.post("/logout")
async def logout(request: Request, identity=Depends(authenticated_identity)):
    require_csrf(request)
    request.session.clear()
    return {"status": "signed_out"}
