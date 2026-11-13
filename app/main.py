"""ChainScope X web application with the existing R0 page and R5 API."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
app.include_router(api_v1_router)
app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "frontend" / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={"title": "ChainScope X"})


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal liveness response; no dependency checks are implied."""
    return {"status": "ok", "service": "chainscope-x"}
