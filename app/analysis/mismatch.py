"""Deterministic declaration-versus-observation comparison over R2 reports."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Iterable

from app.analysis.models import EffectMismatch, MismatchCategory
from app.core.schemas.contracts import (
    Assessment, CoverageStatus, EffectType, ToolManifest,
)


_OPERATION_RULES: dict[tuple[str, str], tuple[str, str]] = {
    ("document-reader", "read_synthetic_asset"): ("read_document", "asset-store.read"),
    ("database-search", "search_synthetic_database"): ("search_database", "synthetic-database.search"),
    ("data-transformer", "read_synthetic_asset"): ("transform_data", "asset-store.read"),
    ("data-transformer", "transform_synthetic_assets"): ("transform_data", "report.transform"),
    ("data-transformer", "create_synthetic_file"): ("create_report", "workspace.create"),
    ("file-creator", "read_synthetic_asset"): ("create_file", "asset-store.read"),
    ("file-creator", "create_synthetic_file"): ("create_file", "workspace.create"),
    ("workspace-storage", "read_controlled_workspace_file"): ("save_internal_file", "workspace.read"),
    ("workspace-storage", "store_internal_synthetic_file"): ("save_internal_file", "workspace.write"),
    ("workspace-storage", "send_to_simulated_destination"): ("share_file", "destination.transmit"),
    ("file-sharing", "read_controlled_workspace_file"): ("share_file", "workspace.read"),
    ("file-sharing", "send_to_simulated_destination"): ("share_file", "destination.transmit"),
}

_REQUIRED_SCOPE: dict[tuple[str, EffectType], str] = {
    ("document-reader", EffectType.READS): "asset-store.read",
    ("data-transformer", EffectType.READS): "asset-store.read",
    ("data-transformer", EffectType.TRANSFORMS): "report-transformer.transform",
    ("data-transformer", EffectType.CREATES): "controlled-workspace.create",
    ("file-creator", EffectType.READS): "asset-store.read",
    ("file-creator", EffectType.CREATES): "controlled-workspace.create",
    ("database-search", EffectType.SEARCHES): "synthetic-database.search",
    ("workspace-storage", EffectType.READS): "controlled-workspace.read",
    ("workspace-storage", EffectType.WRITES): "controlled-workspace.write",
    ("workspace-storage", EffectType.TRANSMITS): "simulated-destination.transmit",
    ("file-sharing", EffectType.READS): "controlled-workspace.read",
    ("file-sharing", EffectType.TRANSMITS): "simulated-destination.transmit",
}


class EffectMismatchAnalyzer:
    @staticmethod
    def required_effects(manifest: ToolManifest) -> frozenset[EffectType]:
        """Only declared, non-optional effects are required for a successful invocation."""
        return frozenset(manifest.declared_effects) - frozenset(manifest.optional_effects)

    @staticmethod
    def _resource_allowed(resource_id: str, manifest: ToolManifest) -> bool:
        if resource_id in manifest.allowed_resources:
            return True
        # R2 file/report identifiers are children of its explicitly allowed workspace root.
        has_workspace_root = any(item.startswith("workspace:") for item in manifest.allowed_resources)
        return has_workspace_root and resource_id.startswith(("file:", "stored:", "report:"))

    @staticmethod
    def _mismatch(*, category: MismatchCategory, execution_id: str, tool_id: str,
                  invocation_ids: Iterable[str] = (), event_ids: Iterable[str] = (),
                  evidence_ids: Iterable[str] = (), expected_effect: EffectType | None = None,
                  observed_effect: EffectType | None = None, resource_ids: Iterable[str] = (),
                  destination_ids: Iterable[str] = (), coverage_status: CoverageStatus,
                  explanation: str, assessment: Assessment | None = None) -> EffectMismatch:
        invocation_ids = sorted(set(invocation_ids))
        event_ids = list(dict.fromkeys(event_ids))
        evidence_ids = sorted(set(evidence_ids))
        resource_ids = sorted(set(resource_ids))
        destination_ids = sorted(set(destination_ids))
        material = "|".join((execution_id, category.value, tool_id, ",".join(invocation_ids),
                             ",".join(event_ids), expected_effect.value if expected_effect else "",
                             observed_effect.value if observed_effect else "",
                             ",".join(resource_ids), ",".join(destination_ids)))
        mismatch_id = "mismatch:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        if assessment is None:
            assessment = (Assessment.INCONCLUSIVE if category == MismatchCategory.INCOMPLETE_COMPARISON
                          else Assessment.EFFECT_MISMATCH)
        return EffectMismatch(
            mismatch_id=mismatch_id, category=category, execution_id=execution_id, tool_id=tool_id,
            invocation_ids=invocation_ids, event_ids=event_ids, evidence_ids=evidence_ids,
            expected_effect=expected_effect, observed_effect=observed_effect,
            resource_ids=resource_ids, destination_ids=destination_ids,
            assessment=assessment, coverage_status=coverage_status, explanation=explanation,
        )

    def analyze(self, report, manifests: Iterable[ToolManifest], valid_events, *,
                integrity_complete: bool = True) -> tuple[EffectMismatch, ...]:
        execution_id = report.execution.execution_id
        coverage = report.coverage
        manifest_list = tuple(manifests)
        manifest_counts: dict[str, int] = defaultdict(int)
        for item in manifest_list:
            manifest_counts[item.tool_id] += 1
        manifest_by_id = {item.tool_id: item for item in manifest_list
                          if manifest_counts[item.tool_id] == 1}
        events_by_invocation = defaultdict(list)
        mismatches: dict[tuple, EffectMismatch] = {}

        def add(item: EffectMismatch) -> None:
            key = (item.category, item.tool_id, tuple(item.invocation_ids), tuple(item.event_ids),
                   item.expected_effect, item.observed_effect, tuple(item.resource_ids),
                   tuple(item.destination_ids))
            mismatches.setdefault(key, item)

        for event in valid_events:
            manifest = manifest_by_id.get(event.tool_id)
            if manifest is None:
                add(self._mismatch(
                    category=MismatchCategory.INCOMPLETE_COMPARISON, execution_id=execution_id,
                    tool_id=event.tool_id, invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                    evidence_ids=[ref.evidence_id for ref in event.evidence], observed_effect=event.effect_type,
                    coverage_status=coverage.status,
                    explanation="The event is traceable, but no supplied manifest resolves its tool identity.",
                ))
                continue
            events_by_invocation[event.invocation_id].append(event)
            if event.effect_type not in manifest.declared_effects:
                add(self._mismatch(
                    category=MismatchCategory.UNDECLARED_OBSERVED_EFFECT, execution_id=execution_id,
                    tool_id=event.tool_id, invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                    evidence_ids=[ref.evidence_id for ref in event.evidence],
                    observed_effect=event.effect_type,
                    resource_ids=[item for item in (event.source_resource, event.destination_resource) if item],
                    destination_ids=[event.destination_resource] if event.destination_resource and
                                    event.destination_resource.startswith("destination:") else [],
                    coverage_status=coverage.status,
                    explanation="A resolving observed event has an effect absent from the tool manifest.",
                ))

            operation_rule = _OPERATION_RULES.get((event.tool_id, event.operation))
            if operation_rule is None:
                add(self._mismatch(
                    category=MismatchCategory.UNEXPECTED_OPERATION, execution_id=execution_id,
                    tool_id=event.tool_id, invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                    evidence_ids=[ref.evidence_id for ref in event.evidence], observed_effect=event.effect_type,
                    coverage_status=coverage.status,
                    explanation="The recorded operation has no approved R2 tool/capability mapping.",
                ))
            else:
                capability, required_permission = operation_rule
                if capability not in manifest.declared_capabilities or required_permission not in manifest.permission_scope:
                    add(self._mismatch(
                        category=MismatchCategory.UNEXPECTED_OPERATION, execution_id=execution_id,
                        tool_id=event.tool_id, invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                        evidence_ids=[ref.evidence_id for ref in event.evidence], observed_effect=event.effect_type,
                        coverage_status=coverage.status,
                        explanation="The operation is not supported by the manifest's declared capability and permission scope.",
                    ))

            unexpected_resources: list[str] = []
            unresolved = False
            if event.source_resource:
                if event.source_resource == "resource:unresolved":
                    unresolved = True
                elif not self._resource_allowed(event.source_resource, manifest):
                    unexpected_resources.append(event.source_resource)
            if event.destination_resource:
                destination = event.destination_resource
                if destination == "destination:unresolved" or destination == "resource:unresolved":
                    unresolved = True
                elif destination.startswith("destination:"):
                    if destination not in manifest.allowed_destinations:
                        unexpected_resources.append(destination)
                elif not self._resource_allowed(destination, manifest):
                    unexpected_resources.append(destination)
            if unexpected_resources:
                add(self._mismatch(
                    category=MismatchCategory.UNEXPECTED_RESOURCE_OR_DESTINATION,
                    execution_id=execution_id, tool_id=event.tool_id,
                    invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                    evidence_ids=[ref.evidence_id for ref in event.evidence], observed_effect=event.effect_type,
                    resource_ids=[item for item in (event.source_resource, event.destination_resource) if item],
                    destination_ids=[item for item in unexpected_resources if item.startswith("destination:")],
                    coverage_status=coverage.status,
                    explanation="The observed resource or destination is outside the manifest's explicit allowlist.",
                ))
            if unresolved:
                add(self._mismatch(
                    category=MismatchCategory.INCOMPLETE_COMPARISON, execution_id=execution_id,
                    tool_id=event.tool_id, invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                    evidence_ids=[ref.evidence_id for ref in event.evidence], observed_effect=event.effect_type,
                    coverage_status=coverage.status,
                    explanation="A resource identity was redacted or unresolved, so the scope comparison is incomplete.",
                ))

        invocation_by_id = {item.invocation_id: item for item in report.invocations}
        for invocation in report.invocations:
            manifest = manifest_by_id.get(invocation.tool_id)
            if manifest is None:
                add(self._mismatch(
                    category=MismatchCategory.INCOMPLETE_COMPARISON, execution_id=execution_id,
                    tool_id=invocation.tool_id, invocation_ids=[invocation.invocation_id],
                    evidence_ids=[invocation.failure_evidence_id] if invocation.failure_evidence_id else [],
                    coverage_status=coverage.status,
                    explanation="No supplied manifest resolves this invocation; declared-effect comparison is incomplete.",
                ))
                continue
            observed = events_by_invocation.get(invocation.invocation_id, [])
            successful_effects = {event.effect_type for event in observed if event.outcome == "SUCCESS"}
            failed_effects = {event.effect_type for event in observed if event.outcome == "FAILED"}
            for expected in sorted(self.required_effects(manifest), key=lambda item: item.value):
                if expected in successful_effects:
                    continue
                scope_id = _REQUIRED_SCOPE.get((invocation.tool_id, expected))
                evidence_ids = list(coverage.evidence_ids)
                if invocation.failure_evidence_id:
                    evidence_ids.append(invocation.failure_evidence_id)
                event_ids = [event.event_id for event in observed if event.effect_type == expected]
                if invocation.status != "SUCCEEDED":
                    category = MismatchCategory.INCOMPLETE_COMPARISON
                    explanation = "The invocation did not complete successfully; a missing effect is not classified as misconduct."
                elif expected in failed_effects:
                    category = MismatchCategory.INCOMPLETE_COMPARISON
                    explanation = "A failed effect event does not establish successful completion of the expected effect."
                elif (integrity_complete and coverage.status == CoverageStatus.COMPLETE and scope_id
                      and scope_id in coverage.monitored_scope):
                    category = MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED
                    explanation = "A successful invocation omitted a required declared effect within its COMPLETE monitored interface."
                else:
                    category = MismatchCategory.INCOMPLETE_COMPARISON
                    explanation = "The required effect is absent, but the invocation or relevant monitoring scope cannot establish a confirmed mismatch."
                add(self._mismatch(
                    category=category, execution_id=execution_id, tool_id=invocation.tool_id,
                    invocation_ids=[invocation.invocation_id], event_ids=event_ids,
                    evidence_ids=evidence_ids, expected_effect=expected,
                    coverage_status=coverage.status, explanation=explanation,
                ))

        return tuple(sorted(mismatches.values(), key=lambda item: (
            item.category.value, item.tool_id, tuple(item.invocation_ids), tuple(item.event_ids),
            item.expected_effect.value if item.expected_effect else "",
        )))
