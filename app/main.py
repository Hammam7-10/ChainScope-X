"""ChainScope X web application with the existing R0 page and R5 API."""
from contextlib import asynccontextmanager
import os
import secrets
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.v1 import router as api_v1_router

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    yield
    service = getattr(application.state, "r5_persistence_service", None)
    close = getattr(service, "close", None)
    if close is not None:
        await close()


app = FastAPI(title="ChainScope X", version="0.1.0", docs_url=None,
              redoc_url=None, lifespan=lifespan)
_env = os.getenv("APP_ENV", "development").strip().lower()
_secure_cookie = os.getenv("CHAIN_SCOPE_SECURE_COOKIES", "").strip().lower()
_https_only = (_secure_cookie in {"1", "true", "yes"}) if _secure_cookie else _env not in {"development", "dev", "test"}
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("CHAIN_SCOPE_SESSION_SECRET", "") or secrets.token_urlsafe(32),
    session_cookie="chainscope_session",
    max_age=int(os.getenv("CHAIN_SCOPE_SESSION_MAX_AGE", "28800")),
    same_site="lax",
    https_only=_https_only,
)
app.include_router(api_v1_router)
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "frontend" / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={"title": "ChainScope X"})


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal liveness response; no dependency checks are implied."""
    return {"status": "ok", "service": "chainscope-x"}
