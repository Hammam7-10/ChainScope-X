"""Authenticated Jinja application pages for the R7 local dashboard."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.security.dependencies import authenticated_identity
from app.security.rbac import has_permission
from app.api.v1 import get_service

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "frontend" / "templates"))

PAGES = {
    "dashboard": ("Dashboard", "Overview of persisted analysis activity and dependency status."),
    "analysis-new": ("New Analysis", "Submit a bounded scenario to the deterministic analysis workflow."),
    "runs": ("Analysis Runs", "Browse persisted analysis runs and their actual workflow states."),
    "findings": ("Findings Explorer", "Explore persisted findings with their evidence-backed classifications."),
    "policies": ("Policy Library", "Browse policy metadata stored by the application."),
    "system": ("System Health", "Liveness and configured dependency health are reported separately."),
    "account": ("Account & Access", "Session identity and capabilities for this account."),
}

async def page(request: Request, key: str, identity, **extra) -> HTMLResponse:
    title, description = PAGES[key]
    if key == "analysis-new" and not has_permission(identity.role, "analysis.run"):
        raise HTTPException(status_code=403, detail="Your role cannot run analyses.")
    return templates.TemplateResponse(request=request, name="app.html", context={
        "title": title, "page": key, "description": description,
        "identity": identity, "role": identity.role, **extra,
    })

@router.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"title": "Sign in · ChainScope X"})

@router.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "dashboard", identity)

@router.get("/app/fragments/dashboard-summary", response_class=HTMLResponse)
async def dashboard_summary_fragment(request: Request, identity=Depends(authenticated_identity)):
    service = get_service(request)
    summary = await service.postgres.dashboard_summary()
    return templates.TemplateResponse(request=request, name="dashboard-summary-fragment.html",
                                      context={"summary": summary})

@router.get("/app/analysis/new", response_class=HTMLResponse)
async def analysis_new(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "analysis-new", identity)

@router.get("/app/analysis-runs", response_class=HTMLResponse)
async def runs(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "runs", identity)

@router.get("/app/analysis-runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str, identity=Depends(authenticated_identity)):
    return await page(request, "runs", identity, page="run-detail", run_id=run_id, title="Run Details", description="Persisted run result, findings, coverage and persistence status.")

@router.get("/app/analysis-runs/{run_id}/timeline", response_class=HTMLResponse)
async def timeline(request: Request, run_id: str, identity=Depends(authenticated_identity)):
    return await page(request, "runs", identity, page="timeline", run_id=run_id, title="Execution Timeline", description="Observed execution events and their provenance.")

@router.get("/app/analysis-runs/{run_id}/evidence", response_class=HTMLResponse)
async def run_evidence(request: Request, run_id: str, identity=Depends(authenticated_identity)):
    return await page(request, "runs", identity, page="evidence", run_id=run_id, title="Evidence Explorer", description="Safe metadata and digests; sensitive payloads are not rendered.")

@router.get("/app/findings", response_class=HTMLResponse)
async def findings(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "findings", identity)

@router.get("/app/findings/{finding_id}", response_class=HTMLResponse)
async def finding_detail(request: Request, finding_id: str, identity=Depends(authenticated_identity)):
    return await page(request, "findings", identity, page="finding-detail", finding_id=finding_id, title="Finding Details", description="Finding details and supported evidence references.")

@router.get("/app/policies", response_class=HTMLResponse)
async def policies(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "policies", identity)

@router.get("/app/policies/{document_id}", response_class=HTMLResponse)
async def policy_detail(request: Request, document_id: str, identity=Depends(authenticated_identity)):
    return await page(request, "policies", identity, page="policy-detail", document_id=document_id, title="Policy Details", description="Source metadata, version, status and digest.")

@router.get("/app/system", response_class=HTMLResponse)
async def system(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "system", identity)

@router.get("/app/account", response_class=HTMLResponse)
async def account(request: Request, identity=Depends(authenticated_identity)):
    return await page(request, "account", identity)
