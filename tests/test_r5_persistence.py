from __future__ import annotations

import asyncio
import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.contracts import AgentRequest
from app.database.models import Base
from app.database.mongo import MongoDocumentStore
from app.database.postgres import PostgresRepository
from app.main import app
from app.persistence.service import R5PersistenceService


class FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, keys, direction=None):
        if isinstance(keys, str):
            keys = [(keys, direction or 1)]
        for key, direction in reversed(list(keys)):
            def value(item):
                current = item
                for segment in key.split("."):
                    current = current.get(segment) if isinstance(current, dict) else None
                return current
            self.items.sort(key=value, reverse=direction < 0)
        return self

    def skip(self, value):
        self.items = self.items[value:]
        return self

    def limit(self, value):
        self.items = self.items[:value]
        return self

    async def to_list(self, length=None):
        return copy.deepcopy(self.items[:length] if length is not None else self.items)


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.indexes = []
        self.fail_writes = False

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))
        return "_".join(item[0] for item in keys)

    async def replace_one(self, query, document, upsert=False):
        if self.fail_writes:
            raise RuntimeError("simulated Mongo outage")
        key = query["_id"]
        if key not in self.documents and not upsert:
            return None
        self.documents[key] = copy.deepcopy(document)
        return None

    async def count_documents(self, query):
        return sum(1 for item in self.documents.values() if item.get("run_id") == query.get("run_id"))

    def find(self, query, projection=None):
        items = [copy.deepcopy(item) for item in self.documents.values()
                 if item.get("run_id") == query.get("run_id")]
        if projection and projection.get("_id") == 0:
            for item in items:
                item.pop("_id", None)
        return FakeCursor(items)


class FakeAdmin:
    async def command(self, name):
        assert name == "ping"
        return {"ok": 1}


class FakeDatabase:
    def __init__(self):
        self.collections = {}
        self.admin = FakeAdmin()

    def __getitem__(self, name):
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


class FakeMongoClient:
    def __init__(self):
        self.databases = {}
        self.admin = FakeAdmin()
        self.closed = False

    def __getitem__(self, name):
        self.databases.setdefault(name, FakeDatabase())
        return self.databases[name]

    async def close(self):
        self.closed = True


class StaticWorkflow:
    def __init__(self, state=None):
        self.state = state or {"workflow_status": "REJECTED", "error_codes": ["fixture_rejected"]}
        self.inactive_policy_document_ids = None

    def invoke(self, request, *, inactive_policy_document_ids=()):
        self.inactive_policy_document_ids = set(inactive_policy_document_ids)
        return self.state


def make_repository():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def create_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    asyncio.run(create_schema())
    return PostgresRepository("", engine=engine)


def make_fake_mongo():
    client = FakeMongoClient()
    return MongoDocumentStore("mongodb://unused", "test", client=client), client


def test_postgres_repository_preserves_run_finding_and_evidence_relationships_and_is_idempotent():
    repo = make_repository()
    async def scenario():
        await repo.create_run(run_id="run-1", request_payload={"scenario_id": "C"},
                              scenario_id="C", planner_mode="mock")
        evidence = [{"evidence_id": "evidence:1", "kind": "recorder", "sha256": "a" * 64,
                     "recorded_at": "2026-11-14T00:00:00+00:00", "classification": "CONFIDENTIAL"}]
        finding = [{"finding_id": "finding:1", "execution_id": "execution:1",
                    "finding_type": "POLICY_VIOLATION", "assessment": "CONFIRMED_VIOLATION",
                    "severity": "HIGH", "classification": "CONFIDENTIAL", "status": "OPEN",
                    "summary": "Evidence-backed finding", "evidence_ids": ["evidence:1"],
                    "payload": {"finding_id": "finding:1"}}]
        await repo.stage_result("run-1", execution_id="execution:1", workflow_status="COMPLETED",
                                planner_mode="mock", result_payload={"analysis": {"status": "CONFIRMED_VIOLATION"}},
                                retry_payload={"events": []}, error_codes=[])
        for _ in range(2):
            await repo.finalize_run("run-1", status="COMPLETED", workflow_status="COMPLETED",
                                    result_payload={"analysis": {"status": "CONFIRMED_VIOLATION"}},
                                    execution_id="execution:1", findings=finding,
                                    evidence_references=evidence)
        run = await repo.get_run("run-1")
        rows = await repo.get_findings("run-1", offset=0, limit=10)
        refs = await repo.get_evidence_references("run-1", offset=0, limit=10)
        assert run["status"] == "COMPLETED"
        assert rows["total"] == 1 and rows["items"][0]["classification"] == "CONFIDENTIAL"
        assert refs["total"] == 1 and refs["items"][0]["sha256"] == "a" * 64
        await repo.close()
    asyncio.run(scenario())


def test_mongo_async_adapter_uses_stable_ids_indexes_and_paginated_reads():
    mongo, client = make_fake_mongo()
    async def scenario():
        payload = {"event_id": "event:1", "execution_id": "execution:1", "invocation_id": "invocation:1",
                  "tool_id": "file-sharing", "sequence": 1, "classification": "CONFIDENTIAL"}
        evidence = {"evidence_id": "evidence:1", "kind": "recorder", "sha256": "a" * 64,
                    "recorded_at": "2026-11-14T00:00:00+00:00", "classification": "CONFIDENTIAL",
                    "payload": {"event_id": "event:1"}}
        for _ in range(2):
            await mongo.persist_run_documents("run-1", events=[payload], evidence_documents=[evidence])
        events = await mongo.get_events("run-1", offset=0, limit=1)
        docs = await mongo.get_evidence_documents("run-1", offset=0, limit=1)
        assert events["total"] == 1 and events["items"][0]["provenance"]["invocation_id"] == "invocation:1"
        assert docs["total"] == 1 and docs["items"][0]["sha256"] == "a" * 64
        assert len(mongo.events.indexes) >= 2 and len(mongo.evidence.indexes) >= 3
        await mongo.close()
        assert client.closed
    asyncio.run(scenario())


def test_r5_orchestrator_persists_real_r4_mock_workflow_and_reconciles_partial_mongo_failure(tmp_path):
    from app.agent.workflow import ChainScopeWorkflow

    repo = make_repository()
    mongo, client = make_fake_mongo()
    mongo.events.fail_writes = True
    workflow = ChainScopeWorkflow(persist_directory=tmp_path / "chroma")
    service = R5PersistenceService(repo, mongo, workflow=workflow)
    request = AgentRequest(query="اختبر مسار البيانات السرية إلى الوجهة الخارجية المحاكاة المحظورة.",
                           scenario_id="C", mode="mock")

    async def scenario():
        pending = await service.run_analysis(request)
        assert pending["status"] == "PERSISTENCE_PENDING"
        assert "mongo_persistence_pending" in pending["error_codes"]
        mongo.events.fail_writes = False
        complete = await service.reconcile(pending["run_id"])
        assert complete["status"] == "COMPLETED"
        assert complete["result"]["analysis"]["status"] == "CONFIRMED_VIOLATION"
        assert "query" not in complete["request"]
        assert complete["request"]["query_length"] == len(request.query)
        assert "query" not in complete["result"]
        assert all("untrusted_excerpt" not in citation
                   for citation in complete["result"]["retrieval"]["citations"])
        findings = await repo.get_findings(pending["run_id"], offset=0, limit=20)
        refs = await repo.get_evidence_references(pending["run_id"], offset=0, limit=100)
        events = await mongo.get_events(pending["run_id"], offset=0, limit=100)
        documents = await mongo.get_evidence_documents(pending["run_id"], offset=0, limit=100)
        assert findings["total"] >= 1
        assert refs["total"] >= 1
        assert events["total"] >= 1
        assert documents["total"] >= 1
        assert all(item["event"].get("event_id") for item in events["items"])
        assert all(len(item["sha256"]) == 64 for item in documents["items"])
        await repo.close()
        await mongo.close()
    asyncio.run(scenario())


def test_api_local_only_guard_and_pagination(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("HOST", "127.0.0.1")
    with TestClient(app) as client:
        assert client.get("/api/v1/analysis-runs?offset=2&limit=5").status_code == 401
        assert client.get("/api/v1/analysis-runs?limit=1000").status_code == 401
        monkeypatch.setenv("HOST", "0.0.0.0")
        assert client.get("/api/v1/analysis-runs").status_code == 503


def test_api_dependency_health_reports_unconfigured_without_exposing_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.delenv("CHAIN_SCOPE_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("CHAIN_SCOPE_MONGODB_URI", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/v1/health/dependencies")
    assert response.status_code == 200
    assert response.json()["status"] == "unconfigured"
    assert "password" not in response.text.lower()


def test_api_guard_rejects_non_loopback_client_even_with_local_host_setting(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.api.v1 import require_local_development

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("HOST", "127.0.0.1")
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/health/dependencies",
                       "headers": [], "query_string": b"", "client": ("192.0.2.10", 12345),
                       "server": ("127.0.0.1", 8000), "root_path": "", "scheme": "http", "app": app})
    with pytest.raises(HTTPException) as error:
        require_local_development(request)
    assert error.value.status_code == 503


def test_pending_policy_blocks_analysis_and_obsolete_ids_reach_workflow():
    from app.persistence.service import PolicyLifecyclePending

    repo = make_repository()
    mongo, _ = make_fake_mongo()
    workflow = StaticWorkflow()
    service = R5PersistenceService(repo, mongo, workflow=workflow)
    request = AgentRequest(query="تأكد من حالة السياسة قبل التشغيل.", scenario_id="A", mode="mock")

    async def scenario():
        metadata = {"document_id": "DOC-STATE-001", "version": "1.0",
                    "document_status": "INDEXING_PENDING", "access_classification": "INTERNAL",
                    "source": "policy/state.md", "content_sha256": "c" * 64}
        await repo.upsert_policy_metadata(metadata)
        with pytest.raises(PolicyLifecyclePending):
            await service.run_analysis(request)
        assert workflow.inactive_policy_document_ids is None
        metadata["document_status"] = "OBSOLETE"
        await repo.upsert_policy_metadata(metadata)
        run = await service.run_analysis(request)
        assert run["status"] == "REJECTED"
        assert workflow.inactive_policy_document_ids == {"DOC-STATE-001"}
        await repo.close()
        await mongo.close()

    asyncio.run(scenario())


def test_policy_search_reapplies_database_obsolete_state_before_retrieval():
    repo = make_repository()
    mongo, _ = make_fake_mongo()

    class FakeStore:
        def __init__(self):
            self.deactivated = []
            self.searched = False

        def deactivate_document(self, document_id):
            self.deactivated.append(document_id)
            return 1, {"document_id": document_id, "document_status": "OBSOLETE"}

        def retrieve(self, query, *, clearance, top_k):
            self.searched = True
            return []

    class FakeWorkflow:
        def __init__(self, store):
            self.store = store

        def _ensure_store(self):
            return self.store

    store = FakeStore()
    service = R5PersistenceService(repo, mongo, workflow=FakeWorkflow(store))

    async def scenario():
        await repo.upsert_policy_metadata({
            "document_id": "DOC-OLD-001", "version": "1.0", "document_status": "OBSOLETE",
            "access_classification": "INTERNAL", "source": "policy/old.md",
            "content_sha256": "d" * 64,
        })
        assert await service.search_policies("test policy query", clearance="INTERNAL", top_k=4) == []
        assert store.deactivated == ["DOC-OLD-001"]
        assert store.searched
        await repo.close()
        await mongo.close()

    asyncio.run(scenario())
