"""Unified deterministic R3 analysis service for one actual R2 execution report."""
from __future__ import annotations

import hashlib
from datetime import timezone
from typing import Iterable

from app.analysis.findings import FindingGenerator
from app.analysis.graph import CapabilityGraphBuilder
from app.analysis.integrity import audit_execution_report
from app.analysis.mismatch import EffectMismatchAnalyzer
from app.analysis.models import AnalysisResult, AnalysisStatus, EffectMismatch, MismatchCategory
from app.analysis.policy import PolicyEvaluator
from app.core.schemas.contracts import Assessment, EffectType


class AnalysisService:
    """Analyze one R2 ExecutionReport at a time, preserving execution boundaries."""

    def __init__(self) -> None:
        self.mismatch_analyzer = EffectMismatchAnalyzer()
        self.graph_builder = CapabilityGraphBuilder()
        self.policy_evaluator = PolicyEvaluator()
        self.finding_generator = FindingGenerator()

    def analyze(self, report, manifests: Iterable, policies: Iterable, evidence_store) -> AnalysisResult:
        execution = report.execution
        execution_id = execution.execution_id
        manifest_list = tuple(manifests)
        policy_list = tuple(policies)
        audit = audit_execution_report(report, evidence_store)
        graph = self.graph_builder.build(execution_id, audit.events)
        mismatches = list(self.mismatch_analyzer.analyze(
            report, manifest_list, audit.events, integrity_complete=not audit.issues,
        ))

        read_sources_by_invocation: dict[str, set[str]] = {}
        for event in audit.events:
            if (event.effect_type == EffectType.READS and event.outcome == "SUCCESS"
                    and event.source_resource):
                read_sources_by_invocation.setdefault(event.invocation_id, set()).add(event.source_resource)

        for event in audit.events:
            if event.effect_type != EffectType.TRANSFORMS:
                continue
            lineage = event.metadata.get("source_asset_ids")
            lineage_valid = (isinstance(lineage, list) and bool(lineage)
                             and all(isinstance(item, str) and item for item in lineage)
                             and set(lineage) == read_sources_by_invocation.get(event.invocation_id, set())
                             and event.source_resource in set(lineage))
            if lineage_valid:
                continue
            explanation = "The transform lineage is missing or does not match successful source reads in the same invocation."
            material = f"{execution_id}|{event.tool_id}|{event.invocation_id}|{event.event_id}|lineage"
            mismatches.append(EffectMismatch(
                mismatch_id="mismatch:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
                category=MismatchCategory.INCOMPLETE_COMPARISON, execution_id=execution_id,
                tool_id=event.tool_id, invocation_ids=[event.invocation_id], event_ids=[event.event_id],
                evidence_ids=[ref.evidence_id for ref in event.evidence],
                observed_effect=event.effect_type, assessment=Assessment.INCONCLUSIVE,
                coverage_status=report.coverage.status, explanation=explanation,
            ))

        policy_result = self.policy_evaluator.evaluate(
            policy_list, execution=execution, coverage=report.coverage, events=audit.events,
            nodes=graph.nodes, edges=graph.edges, paths=graph.paths,
            integrity_complete=not audit.issues,
        )
        incomplete_reasons = list(audit.issues) + list(graph.issues) + list(policy_result.issues)
        if report.coverage.status.value != "COMPLETE":
            incomplete_reasons.append("r2_monitoring_coverage_not_complete")
        incomplete_reasons = list(dict.fromkeys(incomplete_reasons))
        mismatches = list({item.mismatch_id: item for item in mismatches}.values())
        mismatches.sort(key=lambda item: (item.category.value, item.tool_id,
                                          tuple(item.invocation_ids), tuple(item.event_ids), item.mismatch_id))

        findings = self.finding_generator.generate(
            execution_id=execution_id, coverage=report.coverage, mismatches=mismatches,
            policy_evaluations=policy_result.evaluations, policies=policy_list,
            events=audit.events, paths=graph.paths, evidence_store=evidence_store,
        )
        if any(item.assessment.value == "CONFIRMED_VIOLATION" for item in findings):
            status = AnalysisStatus.CONFIRMED_VIOLATION
        elif any(item.assessment.value == "POTENTIAL_RISK" for item in findings):
            status = AnalysisStatus.POTENTIAL_RISK
        elif (incomplete_reasons or report.coverage.status.value != "COMPLETE"
              or any(item.category == MismatchCategory.INCOMPLETE_COMPARISON for item in mismatches)):
            status = AnalysisStatus.INCONCLUSIVE
        else:
            status = AnalysisStatus.NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE

        assessed_at = execution.ended_at or execution.started_at
        if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
            assessed_at = assessed_at.replace(tzinfo=timezone.utc)
        return AnalysisResult(
            execution_id=execution_id, status=status, coverage_status=report.coverage.status,
            monitored_scope=list(report.coverage.monitored_scope), mismatches=mismatches,
            graph_nodes=list(graph.nodes), graph_edges=list(graph.edges), paths=list(graph.paths),
            policy_evaluations=list(policy_result.evaluations), findings=list(findings),
            incomplete_reasons=incomplete_reasons, assessed_at=assessed_at,
        )
