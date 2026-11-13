"""Minimal ChainScope X web foundation for R0."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="ChainScope X", version="0.1.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "frontend" / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={"title": "ChainScope X"})


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal liveness response; no dependency checks are implied."""
    return {"status": "ok", "service": "chainscope-x"}
