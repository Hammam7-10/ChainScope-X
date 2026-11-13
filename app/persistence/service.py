"""R5 vertical slice: bounded R4 workflow plus PostgreSQL/Mongo persistence."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import uuid
from typing import Any

from app.agent.contracts import AgentRequest
from app.database.mongo import MongoDocumentStore
from app.database.postgres import PostgresRepository


_CLASS_RANK = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3}


class PersistencePending(RuntimeError):
    pass


class PolicyLifecyclePending(RuntimeError):
    pass


class R5PersistenceService:
    """Coordinates independent databases without claiming a distributed transaction."""

    def __init__(self, postgres: PostgresRepository, mongo: MongoDocumentStore, *,
                 workflow: Any | None = None) -> None:
        self.postgres = postgres
        self.mongo = mongo
        if workflow is None:
            from app.agent.workflow import ChainScopeWorkflow
            workflow = ChainScopeWorkflow()
        self.workflow = workflow
        self._policy_lifecycle_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.mongo.close()
        await self.postgres.close()

    async def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {"postgresql": "unavailable", "mongodb": "unavailable"}
        try:
            await self.postgres.check_health()
            result["postgresql"] = "ok"
        except Exception:
            pass
        try:
            await self.mongo.check_health()
            result["mongodb"] = "ok"
        except Exception:
            pass
        result["status"] = "ok" if all(result[k] == "ok" for k in ("postgresql", "mongodb")) else "degraded"
        return result

    async def run_analysis(self, request: AgentRequest) -> dict[str, Any]:
        async with self._policy_lifecycle_lock:
            return await self._run_analysis_locked(request)

    async def _run_analysis_locked(self, request: AgentRequest) -> dict[str, Any]:
        pending_policies = await self.postgres.get_pending_policy_document_ids()
        if pending_policies:
            raise PolicyLifecyclePending("Policy indexing/deactivation requires reconciliation")
        inactive_policies = await self.postgres.get_inactive_policy_document_ids()
        run_id = uuid.uuid4().hex
        request_payload = {
            "scenario_id": request.scenario_id,
            "clearance": request.clearance.value,
            "mode": request.mode,
            "query_sha256": hashlib.sha256(request.query.encode("utf-8")).hexdigest(),
            "query_length": len(request.query),
        }
        await self.postgres.create_run(run_id=run_id, request_payload=request_payload,
                                       scenario_id=request.scenario_id, planner_mode=request.mode)
        try:
            state = await asyncio.to_thread(
                self.workflow.invoke, request,
                inactive_policy_document_ids=inactive_policies,
            )
        except Exception:
            await self.postgres.mark_failed(run_id, error_code="workflow_execution_failed")
            raise

        report = state.get("final_report")
        if report is None:
            report = {"workflow_status": state.get("workflow_status", "FAILED"),
                      "error_codes": list(state.get("error_codes", [])),
                      "analysis_authority": "R3 AnalysisService"}
        report = self._sanitize_report(report)
        execution_report = state.get("execution_report")
        execution_id = state.get("execution_id")
        if execution_report is not None:
            execution_id = execution_report.execution.execution_id
        events = self._events(execution_report)
        evidence_documents = self._evidence_documents(state.get("evidence_store"), events)
        analysis_payload = report.get("analysis") if isinstance(report, dict) else None
        findings = self._finding_rows(analysis_payload, events) if analysis_payload else []
        evidence_references = self._evidence_references(evidence_documents)
        pending_payload = {
            "events": events, "evidence_documents": evidence_documents,
            "findings": findings, "evidence_references": evidence_references,
            "execution_id": execution_id, "result_payload": report,
            "workflow_status": state.get("workflow_status", report.get("workflow_status", "FAILED")),
            "planner_mode": state.get("planner_mode", request.mode),
            "error_codes": list(state.get("error_codes", [])),
        }
        await self.postgres.stage_result(
            run_id, execution_id=execution_id,
            workflow_status=pending_payload["workflow_status"],
            planner_mode=pending_payload["planner_mode"], result_payload=report,
            retry_payload=pending_payload, error_codes=pending_payload["error_codes"],
        )
        return await self._persist_pending(run_id, pending_payload)

    async def reconcile(self, run_id: str) -> dict[str, Any]:
        payload = await self.postgres.get_retry_payload(run_id)
        if payload is None:
            run = await self.postgres.get_run(run_id)
            if run is None:
                raise KeyError("Analysis run not found")
            if run["status"] != "PERSISTENCE_PENDING":
                return run
            raise PersistencePending("Retry payload is missing")
        return await self._persist_pending(run_id, payload)

    async def _persist_pending(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await self.mongo.persist_run_documents(
                run_id, events=payload.get("events", []),
                evidence_documents=payload.get("evidence_documents", []),
            )
        except Exception:
            # The SQL retry snapshot remains available for an explicit idempotent reconciliation.
            row = await self.postgres.get_run(run_id)
            codes = list((row or {}).get("error_codes", []))
            if "mongo_persistence_pending" not in codes:
                codes.append("mongo_persistence_pending")
            await self.postgres.stage_result(
                run_id, execution_id=payload.get("execution_id"),
                workflow_status=payload.get("workflow_status", "FAILED"),
                planner_mode=payload.get("planner_mode"),
                result_payload=payload.get("result_payload", {}), retry_payload=payload,
                error_codes=codes,
            )
            result = await self.postgres.get_run(run_id)
            return result or {"run_id": run_id, "status": "PERSISTENCE_PENDING"}

        result_status = self._run_status(payload.get("workflow_status", "FAILED"))
        await self.postgres.finalize_run(
            run_id, status=result_status, workflow_status=payload.get("workflow_status", "FAILED"),
            result_payload=payload.get("result_payload", {}),
            execution_id=payload.get("execution_id"), findings=payload.get("findings", []),
            evidence_references=payload.get("evidence_references", []),
            error_codes=payload.get("error_codes", []),
        )
        run = await self.postgres.get_run(run_id)
        return run or {"run_id": run_id, "status": result_status}

    @staticmethod
    def _run_status(workflow_status: str) -> str:
        if workflow_status == "COMPLETED":
            return "COMPLETED"
        if workflow_status == "REJECTED":
            return "REJECTED"
        return "FAILED"

    @staticmethod
    def _sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
        """Persist result provenance without raw user queries or retrieved policy text."""
        safe = copy.deepcopy(report)
        safe.pop("query", None)
        retrieval = safe.get("retrieval")
        if isinstance(retrieval, dict):
            for citation in retrieval.get("citations", []):
                if isinstance(citation, dict):
                    citation.pop("untrusted_excerpt", None)
        return safe

    @staticmethod
    def _events(execution_report: Any | None) -> list[dict[str, Any]]:
        if execution_report is None:
            return []
        return [event.model_dump(mode="json") for event in execution_report.events]

    @staticmethod
    def _evidence_documents(evidence_store: Any | None,
                            events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if evidence_store is None:
            return []
        classifications: dict[str, str] = {}
        for event in events:
            for ref in event.get("evidence", []):
                classifications[ref["evidence_id"]] = event.get("classification")
        documents = []
        for record in evidence_store.records():
            actual = hashlib.sha256(record.canonical_payload.encode("utf-8")).hexdigest()
            if actual != record.sha256:
                raise ValueError("Evidence digest did not verify before persistence")
            documents.append({
                "evidence_id": record.evidence_id, "kind": record.kind,
                "sha256": record.sha256, "recorded_at": record.recorded_at.isoformat(),
                "classification": classifications.get(record.evidence_id),
                "source_provenance": record.payload(), "payload": record.payload(),
            })
        return documents

    @staticmethod
    def _evidence_references(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"evidence_id": item["evidence_id"], "kind": item["kind"],
                 "sha256": item["sha256"], "recorded_at": item["recorded_at"],
                 "source_document_id": None, "classification": item.get("classification")}
                for item in documents]

    @staticmethod
    def _finding_rows(analysis: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        event_by_id = {event["event_id"]: event for event in events}
        rows = []
        for finding in analysis.get("findings", []):
            path = finding.get("path") or {}
            classes = [path.get("source_classification")] if path.get("source_classification") else []
            classes.extend(event_by_id[event_id].get("classification") for event_id in finding.get("event_ids", [])
                           if event_id in event_by_id)
            classes = [item for item in classes if item in _CLASS_RANK]
            classification = max(classes, key=_CLASS_RANK.__getitem__) if classes else None
            rows.append({
                "finding_id": finding["finding_id"], "execution_id": finding["execution_id"],
                "finding_type": finding["finding_type"], "assessment": finding["assessment"],
                "severity": finding["severity"], "classification": classification,
                "status": finding.get("status", "OPEN"), "summary": finding.get("summary", ""),
                "evidence_ids": list(dict.fromkeys(finding.get("evidence_ids", []))),
                "payload": finding,
            })
        return rows

    async def index_policy(self, relative_path: str) -> dict[str, Any]:
        from app.rag.policy_service import PolicyVectorService
        async with self._policy_lifecycle_lock:
            store = self.workflow._ensure_store()
            service = PolicyVectorService(store, self.workflow.policy_directory)
            document = await asyncio.to_thread(service.prepare_approved_file, relative_path)
            pending = document.metadata.model_dump(mode="json")
            pending["content_sha256"] = document.content_sha256
            pending["document_status"] = "INDEXING_PENDING"
            await self.postgres.upsert_policy_metadata(pending)
            result = await asyncio.to_thread(service.ingest_prepared, document)
            await self.postgres.upsert_policy_metadata(result["metadata"])
            return result

    async def deactivate_policy(self, document_id: str) -> dict[str, Any]:
        from app.rag.policy_service import PolicyVectorService
        async with self._policy_lifecycle_lock:
            store = self.workflow._ensure_store()
            service = PolicyVectorService(store, self.workflow.policy_directory)
            metadata = await asyncio.to_thread(service.get_document_metadata, document_id)
            if metadata is None:
                raise KeyError("Policy document not found in vector index")
            pending = dict(metadata)
            pending["document_status"] = "DEACTIVATION_PENDING"
            await self.postgres.upsert_policy_metadata(pending)
            result = await asyncio.to_thread(service.deactivate, document_id)
            await self.postgres.upsert_policy_metadata(result["metadata"])
            return result

    async def search_policies(self, query: str, *, clearance: str, top_k: int) -> list[dict[str, Any]]:
        from app.core.schemas.contracts import Classification
        async with self._policy_lifecycle_lock:
            if await self.postgres.get_pending_policy_document_ids():
                raise PolicyLifecyclePending("Policy indexing/deactivation requires reconciliation")
            inactive = await self.postgres.get_inactive_policy_document_ids()
            store = self.workflow._ensure_store()
            for document_id in inactive:
                await asyncio.to_thread(store.deactivate_document, document_id)
            passages = await asyncio.to_thread(
                store.retrieve, query, clearance=Classification(clearance), top_k=top_k,
            )
            return [{"chunk_id": item.chunk_id, "text": item.text,
                     "distance": item.distance, "metadata": item.metadata} for item in passages]
