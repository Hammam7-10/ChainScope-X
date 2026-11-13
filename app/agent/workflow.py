"""Single bounded LangGraph workflow: RAG -> allowlisted R2 execution -> deterministic R3."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agent.contracts import AgentRequest, ProposedPlan, SCENARIO_REQUIRED_DOCUMENT
from app.agent.plan_validation import PlanRejection, resolve_action_arguments, validate_plan
from app.agent.planners import GroqPlanner, LiveModelUnavailable, MockPlanner
from app.analysis.service import AnalysisService
from app.rag.policy_catalog import load_policy_catalog
from app.rag.store import PolicyRAGStore
from app.sandbox.runner import ExecutionReport, LabRunner, default_monitored_scope
from app.tools.registry import ToolRegistry, build_default_registry


class AgentState(TypedDict, total=False):
    request: dict[str, Any]
    workflow_status: str
    error_codes: list[str]
    validated_request: dict[str, Any]
    retrieved_context: list[dict[str, Any]]
    registry_snapshot: list[dict[str, Any]]
    policies: tuple[Any, ...]
    policy_sources: dict[str, dict[str, str]]
    plan: dict[str, Any]
    plan_validated: bool
    execution_id: str
    execution_report: ExecutionReport
    evidence_store: Any
    analysis: Any
    planner_mode: str
    model_id: str | None
    live_model_verified: bool
    final_report: dict[str, Any]


class ChainScopeWorkflow:
    """Orchestrate a single bounded synthetic test; no checkpoint or external DB."""

    def __init__(self, *, store: PolicyRAGStore | None = None,
                 registry: ToolRegistry | None = None,
                 policy_directory: str | Path | None = None,
                 persist_directory: str | Path | None = None,
                 analysis_service: AnalysisService | None = None) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        self.policy_directory = Path(policy_directory or os.getenv(
            "CHAIN_SCOPE_POLICY_DIR", str(self.project_root / "data" / "policies")))
        self.store = store
        self.persist_directory = persist_directory
        self.index_report = ()
        self._store_lock = threading.Lock()
        self.registry = registry or build_default_registry()
        self.analysis_service = analysis_service or AnalysisService()
        self.graph = self._build_graph()

    @staticmethod
    def _preflight_route(state: AgentState) -> str:
        return "continue" if state.get("workflow_status") == "READY" else "stop"

    @staticmethod
    def _execution_route(state: AgentState) -> str:
        return "continue" if state.get("execution_report") is not None else "stop"

    @staticmethod
    def _analysis_route(state: AgentState) -> str:
        return "continue" if state.get("analysis") is not None else "stop"

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("validate_request", self._validate_request)
        builder.add_node("retrieve_policy", self._retrieve_policy)
        builder.add_node("inspect_registry", self._inspect_registry)
        builder.add_node("plan_test", self._plan_test)
        builder.add_node("validate_plan", self._validate_plan)
        builder.add_node("execute_tools", self._execute_tools)
        builder.add_node("analyze_execution", self._analyze_execution)
        builder.add_node("evidence_report", self._evidence_report)
        builder.set_entry_point("validate_request")
        builder.add_conditional_edges("validate_request", self._preflight_route,
                                      {"continue": "retrieve_policy", "stop": END})
        builder.add_conditional_edges("retrieve_policy", self._preflight_route,
                                      {"continue": "inspect_registry", "stop": END})
        builder.add_conditional_edges("inspect_registry", self._preflight_route,
                                      {"continue": "plan_test", "stop": END})
        builder.add_conditional_edges("plan_test", self._preflight_route,
                                      {"continue": "validate_plan", "stop": END})
        builder.add_conditional_edges("validate_plan", self._preflight_route,
                                      {"continue": "execute_tools", "stop": END})
        builder.add_conditional_edges("execute_tools", self._execution_route,
                                      {"continue": "analyze_execution", "stop": END})
        builder.add_conditional_edges("analyze_execution", self._analysis_route,
                                      {"continue": "evidence_report", "stop": END})
        builder.add_edge("evidence_report", END)
        return builder.compile()

    @staticmethod
    def _error(state: AgentState, code: str, *, status: str = "FAILED", **extra: Any) -> dict[str, Any]:
        codes = list(state.get("error_codes", []))
        if code not in codes:
            codes.append(code)
        return {"workflow_status": status, "error_codes": codes, **extra}

    def _validate_request(self, state: AgentState) -> dict[str, Any]:
        try:
            request = AgentRequest.model_validate(state.get("request", {}))
        except Exception:
            return self._error(state, "invalid_request", status="REJECTED")
        return {"validated_request": request.model_dump(mode="json"), "workflow_status": "READY",
                "error_codes": [], "planner_mode": request.mode, "live_model_verified": False}

    def _ensure_store(self) -> PolicyRAGStore:
        with self._store_lock:
            if self.store is None:
                self.store = PolicyRAGStore(persist_directory=self.persist_directory)
            self.index_report = self.store.sync_directory(self.policy_directory)
            return self.store

    def _retrieve_policy(self, state: AgentState) -> dict[str, Any]:
        request = AgentRequest.model_validate(state["validated_request"])
        try:
            store = self._ensure_store()
            passages = store.retrieve(request.query, clearance=request.clearance, top_k=4)
        except Exception:
            return self._error(state, "rag_retrieval_failed")
        if not passages:
            return self._error(state, "rag_no_accessible_policy_context")
        context = [{
            "text": passage.text,
            "distance": passage.distance,
            "metadata": dict(passage.metadata),
        } for passage in passages]
        return {"retrieved_context": context, "workflow_status": "READY"}

    def _inspect_registry(self, state: AgentState) -> dict[str, Any]:
        try:
            manifests = self.registry.list_manifests()
            if len(manifests) != 6 or any(item.status != "ACTIVE" for item in manifests):
                return self._error(state, "approved_registry_invalid")
            catalog = load_policy_catalog(self.policy_directory)
        except Exception:
            return self._error(state, "registry_or_policy_catalog_invalid")
        return {
            "registry_snapshot": [item.model_dump(mode="json") for item in manifests],
            "policies": catalog.rules,
            "policy_sources": catalog.source_by_rule_id,
            "workflow_status": "READY",
        }

    def _plan_test(self, state: AgentState) -> dict[str, Any]:
        request = AgentRequest.model_validate(state["validated_request"])
        required_document = SCENARIO_REQUIRED_DOCUMENT[request.scenario_id]
        if not any(item.get("metadata", {}).get("document_id") == required_document
                   for item in state.get("retrieved_context", [])):
            return self._error(state, "rag_context_not_relevant")
        if request.mode == "mock":
            planner = MockPlanner()
        else:
            planner = GroqPlanner()
        try:
            proposal = planner.propose(request, state["registry_snapshot"], state["retrieved_context"])
        except LiveModelUnavailable:
            return self._error(state, "live_model_unavailable_or_request_failed",
                               planner_mode=request.mode, model_id=getattr(planner, "model_id", None),
                               live_model_verified=False)
        except Exception:
            return self._error(state, "planner_failed", planner_mode=request.mode,
                               live_model_verified=False)
        return {
            "plan": proposal.model_dump(mode="json"),
            "planner_mode": planner.mode,
            "model_id": getattr(planner, "model_id", None),
            "live_model_verified": bool(getattr(planner, "live_model_verified", False)),
            "workflow_status": "READY",
        }

    def _validate_plan(self, state: AgentState) -> dict[str, Any]:
        request = AgentRequest.model_validate(state["validated_request"])
        try:
            plan = validate_plan(state["plan"], scenario_id=request.scenario_id,
                                 registry=self.registry)
        except PlanRejection as exc:
            return self._error(state, exc.code, status="REJECTED", plan_validated=False)
        except Exception:
            return self._error(state, "plan_rejected", status="REJECTED", plan_validated=False)
        return {"plan": plan.model_dump(mode="json"), "plan_validated": True,
                "workflow_status": "READY"}

    def _execute_tools(self, state: AgentState) -> dict[str, Any]:
        request = AgentRequest.model_validate(state["validated_request"])
        plan = ProposedPlan.model_validate(state["plan"])
        runner = LabRunner(registry=self.registry)
        adversarial_fixture = request.scenario_id == "B"
        execution_id = runner.start_execution(
            default_monitored_scope(),
            adversarial_storage_external_copy=adversarial_fixture,
        )
        if request.scenario_id == "D":
            runner.note_coverage_gap(execution_id, "R4_MONITORING_FIXTURE_PARTIAL")
        outputs: list[dict[str, Any]] = []
        for index, action in enumerate(plan.actions):
            try:
                arguments = resolve_action_arguments(plan, index, outputs, self.registry)
            except PlanRejection:
                runner.note_coverage_gap(execution_id, "R4_PLAN_REFERENCE_FAILED")
                break
            result = runner.invoke(execution_id, action.tool_id, arguments)
            outputs.append(result)
            if result.get("status") != "SUCCEEDED":
                break
        report = runner.finish_execution(execution_id)
        return {"execution_id": execution_id, "execution_report": report,
                "evidence_store": runner.evidence_store,
                "workflow_status": "EXECUTED"}

    def _analyze_execution(self, state: AgentState) -> dict[str, Any]:
        report = state["execution_report"]
        runner_evidence_store = state.get("evidence_store")
        if runner_evidence_store is None:
            return self._error(state, "execution_evidence_store_unavailable")
        try:
            result = self.analysis_service.analyze(
                report, self.registry.list_manifests(), state.get("policies", ()), runner_evidence_store)
        except Exception:
            return self._error(state, "r3_analysis_failed")
        return {"analysis": result, "workflow_status": "ANALYZED"}

    @staticmethod
    def _status_ar(value: str) -> str:
        return {
            "NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE": "لم يُرصد انتهاك ضمن النطاق الكامل المحدد.",
            "CONFIRMED_VIOLATION": "أكد محرك R3 مخالفة مدعومة بقاعدة ومسار وحدث وأدلة.",
            "POTENTIAL_RISK": "رُصد خطر محتمل؛ لا يُعرض بوصفه مخالفة مؤكدة.",
            "INCONCLUSIVE": "النتيجة غير حاسمة بسبب نقص أو فجوة في التغطية أو الأدلة.",
        }.get(value, "لا تتوفر نتيجة تحليل موثقة.")

    def _evidence_report(self, state: AgentState) -> dict[str, Any]:
        report: ExecutionReport = state["execution_report"]
        analysis = state["analysis"]
        analysis_payload = analysis.model_dump(mode="json")
        invocations = [{
            "invocation_id": item.invocation_id,
            "tool_id": item.tool_id,
            "status": item.status,
            "error_code": item.error_code,
        } for item in report.invocations]
        events = [{
            "event_id": event.event_id,
            "execution_id": event.execution_id,
            "invocation_id": event.invocation_id,
            "tool_id": event.tool_id,
            "effect_type": event.effect_type.value,
            "source_resource": event.source_resource,
            "destination_resource": event.destination_resource,
            "classification": event.classification.value,
            "outcome": event.outcome,
            "evidence_ids": [reference.evidence_id for reference in event.evidence],
        } for event in report.events]
        citations = []
        seen_chunks = set()
        for passage in state["retrieved_context"]:
            metadata = passage["metadata"]
            key = metadata.get("chunk_id", "")
            if key in seen_chunks:
                continue
            seen_chunks.add(key)
            citations.append({
                "document_id": metadata.get("document_id"),
                "version": metadata.get("version"),
                "source": metadata.get("source"),
                "section": metadata.get("section"),
                "page": metadata.get("page"),
                "chunk_id": key,
                "policy_id": metadata.get("policy_id") or None,
                "access_classification": metadata.get("access_classification"),
                "document_status": metadata.get("document_status"),
                "distance": passage["distance"],
                "untrusted_excerpt": passage["text"][:240],
            })
        result_status = analysis.status.value
        final_report = {
            "workflow_status": "COMPLETED",
            "scenario_id": state["validated_request"]["scenario_id"],
            "query": state["validated_request"]["query"],
            "planner_mode": state.get("planner_mode", "mock"),
            "model_id": state.get("model_id"),
            "live_model_verified": bool(state.get("live_model_verified", False)),
            "plan_validated": bool(state.get("plan_validated", False)),
            "execution": {
                "execution_id": report.execution.execution_id,
                "status": report.execution.status,
                "invocations": invocations,
                "coverage": report.coverage.model_dump(mode="json"),
                "observed_event_count": len(events),
                "observed_events": events,
            },
            "retrieval": {
                "collection": self.store.COLLECTION_NAME if self.store else PolicyRAGStore.COLLECTION_NAME,
                "persistent_directory": str(self.store.persist_directory) if self.store else None,
                "passage_count": len(citations),
                "citations": citations,
                "policy_sources": state.get("policy_sources", {}),
                "retrieved_content_is_untrusted": True,
            },
            "analysis_authority": "R3 AnalysisService",
            "analysis": analysis_payload,
            "summary_ar": self._status_ar(result_status),
        }
        return {"final_report": final_report, "workflow_status": "COMPLETED"}

    def invoke(self, request: AgentRequest | dict[str, Any]) -> AgentState:
        if isinstance(request, AgentRequest):
            payload = request.model_dump(mode="json")
        else:
            payload = dict(request)
        return self.graph.invoke({"request": payload}, config={"recursion_limit": 24})
