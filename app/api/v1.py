"""Development-local R5 API backed by real PostgreSQL, MongoDB and Chroma adapters."""
from __future__ import annotations

import ipaddress
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.agent.contracts import AgentRequest
from app.core.schemas.contracts import Classification
from app.database.config import DatabaseConfig, DatabaseConfigurationError
from app.database.mongo import MongoDocumentStore
from app.database.postgres import PostgresRepository
from app.persistence.service import PersistencePending, PolicyLifecyclePending, R5PersistenceService


router = APIRouter(prefix="/api/v1", tags=["R5 local backend"])


def require_local_development(request: Request) -> None:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    bind_host = os.getenv("HOST", "127.0.0.1").strip().lower()
    client_host = request.client.host if request.client else ""
    try:
        client_ip = ipaddress.ip_address(client_host)
        client_is_loopback = client_ip.is_loopback or bool(
            getattr(client_ip, "ipv4_mapped", None) and client_ip.ipv4_mapped.is_loopback
        )
    except ValueError:
        client_is_loopback = app_env == "test" and client_host == "testclient"
    if (app_env not in {"development", "dev", "test"}
            or bind_host not in {"127.0.0.1", "localhost", "::1"}
            or not client_is_loopback):
        raise HTTPException(status_code=503, detail={
            "code": "local_development_only",
            "message": "R5 persistence endpoints are available only in local development; authentication is not implemented.",
        })


def get_service(request: Request) -> R5PersistenceService:
    require_local_development(request)
    service = getattr(request.app.state, "r5_persistence_service", None)
    if service is not None:
        return service
    try:
        config = DatabaseConfig.from_environment()
    except DatabaseConfigurationError:
        raise HTTPException(status_code=503, detail={
            "code": "database_configuration_missing",
            "message": "PostgreSQL and MongoDB must be configured for R5 persistence.",
        }) from None
    service = R5PersistenceService(
        PostgresRepository(config.postgres_dsn),
        MongoDocumentStore(config.mongodb_uri, config.mongodb_database),
    )
    request.app.state.r5_persistence_service = service
    return service


class PolicyIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_path: str = Field(min_length=1, max_length=500)


@router.get("/health/dependencies", dependencies=[Depends(require_local_development)])
async def dependency_health(request: Request) -> dict[str, Any]:
    service = getattr(request.app.state, "r5_persistence_service", None)
    if service is None:
        try:
            config = DatabaseConfig.from_environment()
            service = R5PersistenceService(
                PostgresRepository(config.postgres_dsn),
                MongoDocumentStore(config.mongodb_uri, config.mongodb_database),
            )
            request.app.state.r5_persistence_service = service
        except DatabaseConfigurationError:
            return {"status": "unconfigured", "postgresql": "not_configured",
                    "mongodb": "not_configured", "chroma": "local_persistent_store",
                    "authentication": "not_implemented_local_only", "local_only": True}
    result = await service.health()
    result["chroma"] = "local_persistent_store"
    result["authentication"] = "not_implemented_local_only"
    return result


@router.post("/analysis-runs", status_code=status.HTTP_201_CREATED)
async def create_analysis_run(payload: AgentRequest,
                              service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    try:
        return await service.run_analysis(payload)
    except PolicyLifecyclePending:
        raise HTTPException(status_code=409, detail={
            "code": "policy_lifecycle_pending",
            "message": "Complete or retry the pending policy indexing/deactivation before running analysis.",
        }) from None
    except Exception:
        raise HTTPException(status_code=503, detail={
            "code": "analysis_run_unavailable",
            "message": "Analysis could not be persisted; inspect dependency health and retry safely.",
        }) from None


@router.get("/analysis-runs")
async def list_analysis_runs(offset: int = Query(default=0, ge=0),
                             limit: int = Query(default=20, ge=1, le=100),
                             service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    return await service.postgres.list_runs(offset=offset, limit=limit)


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str, service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    row = await service.postgres.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Analysis run not found."})
    return row


@router.get("/analysis-runs/{run_id}/findings")
async def get_run_findings(run_id: str, offset: int = Query(default=0, ge=0),
                           limit: int = Query(default=50, ge=1, le=100),
                           service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    result = await service.postgres.get_findings(run_id, offset=offset, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Analysis run not found."})
    return result


@router.get("/analysis-runs/{run_id}/evidence/references")
async def get_run_evidence_references(run_id: str, offset: int = Query(default=0, ge=0),
                                     limit: int = Query(default=50, ge=1, le=100),
                                     service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    result = await service.postgres.get_evidence_references(run_id, offset=offset, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Analysis run not found."})
    return result


@router.get("/analysis-runs/{run_id}/events")
async def get_run_events(run_id: str, offset: int = Query(default=0, ge=0),
                         limit: int = Query(default=50, ge=1, le=100),
                         service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    if await service.postgres.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Analysis run not found."})
    return await service.mongo.get_events(run_id, offset=offset, limit=limit)


@router.get("/analysis-runs/{run_id}/evidence")
async def get_run_evidence(run_id: str, offset: int = Query(default=0, ge=0),
                           limit: int = Query(default=50, ge=1, le=100),
                           service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    if await service.postgres.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Analysis run not found."})
    return await service.mongo.get_evidence_documents(run_id, offset=offset, limit=limit)


@router.post("/analysis-runs/{run_id}/reconcile")
async def reconcile_analysis_run(run_id: str,
                                 service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    try:
        return await service.reconcile(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Analysis run not found."}) from None
    except PersistencePending:
        raise HTTPException(status_code=409, detail={"code": "reconciliation_unavailable", "message": "Retry snapshot is unavailable."}) from None
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "reconciliation_failed", "message": "Persistence reconciliation did not complete."}) from None


@router.post("/policies/index")
async def index_approved_policy(payload: PolicyIndexRequest,
                                service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    try:
        return await service.index_policy(payload.relative_path)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=422, detail={"code": "invalid_policy_source", "message": "Policy source is invalid or not approved."}) from None
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "policy_index_unavailable", "message": "Policy indexing did not complete."}) from None


@router.post("/policies/{document_id}/deactivate")
async def deactivate_policy(document_id: str,
                           service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    try:
        return await service.deactivate_policy(document_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Policy document not found."}) from None
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "policy_deactivation_unavailable", "message": "Policy deactivation did not complete."}) from None


@router.get("/policies/search")
async def search_policy_passages(q: str = Query(min_length=3, max_length=1200),
                                 clearance: Classification = Classification.INTERNAL,
                                 top_k: int = Query(default=4, ge=1, le=10),
                                 service: R5PersistenceService = Depends(get_service)) -> dict[str, Any]:
    try:
        passages = await service.search_policies(q, clearance=clearance.value, top_k=top_k)
    except PolicyLifecyclePending:
        raise HTTPException(status_code=409, detail={
            "code": "policy_lifecycle_pending",
            "message": "Complete or retry the pending policy indexing/deactivation before searching.",
        }) from None
    return {"items": passages, "count": len(passages), "classification_filter_applied": clearance.value}
