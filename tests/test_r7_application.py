from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from fastapi.testclient import TestClient
from app.api.v1 import router as api_router
from app.main import app
from app.security.dependencies import authenticated_identity
from app.web import router as web_router

@dataclass
class Identity:
    user_id: str = "u-test"
    google_subject: str = "google-test"
    email: str = "analyst@example.test"
    name: str = "Test Analyst"
    role: str = "analyst"
    csrf_token: str = "csrf-test"


def test_all_r7_pages_and_login_are_registered():
    paths = {r.path for r in web_router.routes}
    assert {
        "/login", "/app", "/app/analysis/new", "/app/analysis-runs",
        "/app/analysis-runs/{run_id}", "/app/analysis-runs/{run_id}/timeline",
        "/app/analysis-runs/{run_id}/evidence", "/app/findings",
        "/app/findings/{finding_id}", "/app/policies", "/app/policies/{document_id}",
        "/app/system", "/app/account", "/app/fragments/dashboard-summary",
    } <= paths


def test_new_api_contracts_are_registered():
    paths = {r.path for r in api_router.routes}
    assert {
        "/api/v1/dashboard/summary", "/api/v1/findings", "/api/v1/findings/{finding_id}",
        "/api/v1/policies", "/api/v1/policies/{document_id}",
    } <= paths


def test_authenticated_pages_render_local_assets_and_escape_path_values():
    app.dependency_overrides[authenticated_identity] = lambda: Identity()
    try:
        with TestClient(app) as client:
            login = client.get("/login")
            assert login.status_code == 200
            assert "/auth/google/start" in login.text
            assert 'type="password"' not in login.text.lower()
            static = client.get("/static/vendor/htmx.min.js")
            assert static.status_code == 200 and len(static.content) > 10_000
            response = client.get("/app/analysis-runs/%3Cscript%3Ealert(1)%3Cscript%3E")
            assert response.status_code == 200
            assert 'href="/static/css/app.css"' in response.text
            assert 'src="/static/js/app.js"' in response.text
            assert "<script>alert(1)<script>" not in response.text
            assert "data-role=\"analyst\"" in response.text
    finally:
        app.dependency_overrides.clear()


def test_expired_browser_session_redirects_to_google_login():
    with TestClient(app) as client:
        response = client.get("/app", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_frontend_has_no_external_runtime_assets_and_sensitive_evidence_is_not_rendered():
    root = Path(__file__).resolve().parents[1]
    template = (root / "frontend/templates/app.html").read_text()
    script = (root / "frontend/static/js/app.js").read_text()
    assert "https://" not in template
    assert "/static/" in template
    assert "/static/vendor/htmx.min.js" in template
    assert "hx-get=\"/app/fragments/dashboard-summary\"" in script
    assert "localStorage" not in script and "sessionStorage" not in script
    assert "source_provenance:x.source_provenance" not in script
    assert "payload:x.payload" not in script
