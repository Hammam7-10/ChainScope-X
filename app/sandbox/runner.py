"""Execution lifecycle and explicit bounded coverage for the controlled R2 lab."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.schemas.contracts import CoverageRecord, CoverageStatus, EffectType, EvidenceReference, Classification
from app.effects.evidence_store import EvidenceStore
from app.effects.recorder import EffectRecorder, RecorderUnavailable
from app.sandbox.resources import (
    INSTRUMENTED_INTERFACES,
    FixtureOptions, SandboxContext, SyntheticAsset, SyntheticAssetStore,
    SyntheticDatabase, ControlledTransformer, ControlledWorkspace,
    SimulatedDestinationStore,
)
from app.tools.registry import ToolRegistry, UnknownToolError, build_default_registry


@dataclass
class ExecutionRecord:
    execution_id: str
    status: str
    started_at: datetime
    monitored_scope: list[str] | None
    fixtures: FixtureOptions
    self_check: EvidenceReference | None = None
    gaps: list[str] = field(default_factory=list)
    recorder_failed: bool = False
    invocation_ids: list[str] = field(default_factory=list)
    failure_evidence_ids: list[str] = field(default_factory=list)
    ended_at: datetime | None = None
    coverage: CoverageRecord | None = None


@dataclass
class InvocationRecord:
    invocation_id: str
    execution_id: str
    tool_id: str
    status: str = "RUNNING"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    error_code: str | None = None
    failure_evidence_id: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    execution: ExecutionRecord
    invocations: tuple[InvocationRecord, ...]
    events: tuple[Any, ...]
    coverage: CoverageRecord


class LabRunner:
    """Runs only tools in the static registry against local synthetic adapters."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()
        self.evidence_store = EvidenceStore()
        self.recorder = EffectRecorder(self.evidence_store)
        assets = {
            "asset:public:handbook": SyntheticAsset("asset:public:handbook", Classification.PUBLIC,
                {"title": "Synthetic Handbook", "text": "Public sample text for ChainScope tests."}),
            "asset:internal:ops": SyntheticAsset("asset:internal:ops", Classification.INTERNAL,
                {"title": "Synthetic Operations", "summary": "Internal sample process status."}),
            "asset:confidential:case-7": SyntheticAsset("asset:confidential:case-7", Classification.CONFIDENTIAL,
                {"title": "Synthetic Case 7", "summary": "Confidential simulated incident record.",
                 "case_ref": "SYNTH-007"}),
            "asset:restricted:fixture": SyntheticAsset("asset:restricted:fixture", Classification.RESTRICTED,
                {"title": "Restricted Synthetic Fixture", "summary": "Restricted dummy value only.",
                 "fixture_id": "FIXTURE-RESTRICTED-1"}),
        }
        self.assets = SyntheticAssetStore(self.recorder, assets)
        self.database = SyntheticDatabase(self.recorder)
        self.transformer = ControlledTransformer(self.recorder)
        self.workspace = ControlledWorkspace(self.recorder)
        self.destinations = SimulatedDestinationStore(self.recorder)
        self._executions: dict[str, ExecutionRecord] = {}
        self._invocations: dict[str, InvocationRecord] = {}

    def start_execution(self, monitored_scope: list[str] | None = None, *,
                        adversarial_storage_external_copy: bool = False) -> str:
        execution_id = f"execution:{uuid.uuid4().hex}"
        scope = list(monitored_scope) if monitored_scope is not None else None
        execution = ExecutionRecord(execution_id, "RUNNING", datetime.now(timezone.utc), scope,
                                    FixtureOptions(adversarial_storage_external_copy))
        self._executions[execution_id] = execution
        if scope is None or not scope:
            execution.gaps.append("Explicit monitored scope manifest was not provided")
            return execution_id
        unknown = sorted(set(scope) - INSTRUMENTED_INTERFACES)
        if unknown:
            execution.gaps.append("Unrecognized monitored interface(s): " + ",".join(unknown))
        if not self.recorder.active:
            execution.recorder_failed = True
            execution.gaps.append("Recorder inactive at execution start")
            return execution_id
        try:
            execution.self_check = self.recorder.self_check(execution_id, scope)
        except Exception:
            execution.recorder_failed = True
            execution.gaps.append("Recorder self-check failed")
        return execution_id

    def note_coverage_gap(self, execution_id: str, reason_code: str) -> None:
        execution = self._require_active_execution(execution_id)
        safe_code = "".join(ch for ch in reason_code.upper() if ch.isalnum() or ch in "_-")[:64]
        execution.gaps.append("Detected coverage gap: " + (safe_code or "UNSPECIFIED"))

    def _require_active_execution(self, execution_id: str) -> ExecutionRecord:
        execution = self._executions.get(execution_id)
        if execution is None:
            raise KeyError("Execution not found")
        if execution.status != "RUNNING":
            raise RuntimeError("Execution is already closed")
        return execution

    def _failure_evidence(self, execution: ExecutionRecord, invocation: InvocationRecord,
                          error_code: str) -> str | None:
        try:
            known_tool_ids = {manifest.tool_id for manifest in self.registry.list_manifests()}
            safe_tool_id = invocation.tool_id if invocation.tool_id in known_tool_ids else "tool:unresolved"
            ref = self.evidence_store.create("invocation_failure", {
                "execution_id": execution.execution_id,
                "invocation_id": invocation.invocation_id,
                "tool_id": safe_tool_id,
                "reason_code": error_code,
            })
            invocation.failure_evidence_id = ref.evidence_id
            execution.failure_evidence_ids.append(ref.evidence_id)
            return ref.evidence_id
        except Exception:
            execution.recorder_failed = True
            execution.gaps.append("Failure evidence could not be stored")
            return None

    def invoke(self, execution_id: str, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        execution = self._require_active_execution(execution_id)
        invocation_id = f"invocation:{uuid.uuid4().hex}"
        invocation = InvocationRecord(invocation_id, execution_id, tool_id)
        self._invocations[invocation_id] = invocation
        execution.invocation_ids.append(invocation_id)
        try:
            if execution.recorder_failed:
                raise RecorderUnavailable("RECORDER_NOT_READY")
            manifest = self.registry.get_manifest(tool_id)
            context = SandboxContext(
                execution_id=execution_id,
                invocation_id=invocation_id,
                tool_id=tool_id,
                permission_scope=tuple(manifest.permission_scope),
                allowed_resources=tuple(manifest.allowed_resources),
                allowed_destinations=tuple(manifest.allowed_destinations),
                fixtures=execution.fixtures,
                assets=self.assets,
                database=self.database,
                transformer=self.transformer,
                workspace=self.workspace,
                destinations=self.destinations,
            )
            output = self.registry.invoke(tool_id, payload, context)
            invocation.status = "SUCCEEDED"
            return {"invocation_id": invocation_id, "status": invocation.status, "output": output}
        except Exception as exc:
            code = getattr(exc, "code", "TOOL_EXECUTION_FAILED")
            invocation.status = "FAILED"
            invocation.error_code = code
            if isinstance(exc, RecorderUnavailable):
                execution.recorder_failed = True
                execution.gaps.append("Effect recorder failed during a controlled operation")
            self._failure_evidence(execution, invocation, code)
            return {"invocation_id": invocation_id, "status": invocation.status, "error_code": code}
        finally:
            invocation.ended_at = datetime.now(timezone.utc)

    def finish_execution(self, execution_id: str) -> ExecutionReport:
        execution = self._require_active_execution(execution_id)
        execution.ended_at = datetime.now(timezone.utc)
        invocations = tuple(self._invocations[key] for key in execution.invocation_ids)
        execution.status = "COMPLETED" if all(item.status == "SUCCEEDED" for item in invocations) else "FAILED"
        events = self.recorder.events_for(execution_id)

        if execution.recorder_failed or not self.recorder.active:
            coverage_status = CoverageStatus.FAILED
        elif execution.monitored_scope is None or not execution.monitored_scope:
            coverage_status = CoverageStatus.UNKNOWN
        elif execution.gaps:
            coverage_status = CoverageStatus.PARTIAL
        elif (execution.self_check is None or not self.evidence_store.verify(execution.self_check)
              or not self.recorder.evidence_resolves(execution_id)):
            coverage_status = CoverageStatus.FAILED
            execution.gaps.append("Recorder self-check or event evidence integrity could not be verified")
        else:
            coverage_status = CoverageStatus.COMPLETE

        evidence_ids = list(execution.failure_evidence_ids)
        if execution.self_check is not None:
            evidence_ids.append(execution.self_check.evidence_id)
        for event in events:
            evidence_ids.extend(reference.evidence_id for reference in event.evidence)
        evidence_ids = list(dict.fromkeys(evidence_ids))
        execution.coverage = CoverageRecord(
            coverage_id=f"coverage:{uuid.uuid4().hex}",
            execution_id=execution_id,
            status=coverage_status,
            monitored_scope=execution.monitored_scope or [],
            monitored_operations=sorted({event.effect_type.value for event in events}),
            gaps=list(execution.gaps),
            recorder_version=self.recorder.VERSION,
            assessed_at=datetime.now(timezone.utc),
            evidence_ids=evidence_ids,
        )
        return ExecutionReport(execution, invocations, tuple(events), execution.coverage.model_copy(deep=True))

    def get_invocation(self, invocation_id: str) -> InvocationRecord:
        try:
            return self._invocations[invocation_id]
        except KeyError as exc:
            raise KeyError("Invocation not found") from exc

    def asset_ids(self) -> list[str]:
        return ["asset:public:handbook", "asset:internal:ops",
                "asset:confidential:case-7", "asset:restricted:fixture"]


def default_monitored_scope() -> list[str]:
    return sorted(INSTRUMENTED_INTERFACES)
