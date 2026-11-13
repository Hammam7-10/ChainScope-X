"""Additive R3 analysis contracts built on the accepted R1 domain models."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.core.schemas.contracts import (
    Assessment, CapabilityPath, Contract, CoverageStatus, EffectType, Finding,
    GraphEdge, GraphNode, Severity,
)


class AnalysisStatus(StrEnum):
    CONFIRMED_VIOLATION = "CONFIRMED_VIOLATION"
    POTENTIAL_RISK = "POTENTIAL_RISK"
    INCONCLUSIVE = "INCONCLUSIVE"
    NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE = "NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE"


class MismatchCategory(StrEnum):
    UNDECLARED_OBSERVED_EFFECT = "UNDECLARED_OBSERVED_EFFECT"
    EXPECTED_EFFECT_NOT_OBSERVED = "EXPECTED_EFFECT_NOT_OBSERVED"
    UNEXPECTED_RESOURCE_OR_DESTINATION = "UNEXPECTED_RESOURCE_OR_DESTINATION"
    UNEXPECTED_OPERATION = "UNEXPECTED_OPERATION"
    INCOMPLETE_COMPARISON = "INCOMPLETE_COMPARISON"


class PolicyApplicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    INACTIVE = "INACTIVE"
    NOT_YET_EFFECTIVE = "NOT_YET_EFFECTIVE"
    EXPIRED = "EXPIRED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNSUPPORTED_RULE = "UNSUPPORTED_RULE"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class EffectMismatch(Contract):
    mismatch_id: str = Field(min_length=1)
    category: MismatchCategory
    execution_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    invocation_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    expected_effect: EffectType | None = None
    observed_effect: EffectType | None = None
    resource_ids: list[str] = Field(default_factory=list)
    destination_ids: list[str] = Field(default_factory=list)
    assessment: Assessment
    coverage_status: CoverageStatus
    explanation: str = Field(min_length=1)


class PolicyEvaluation(Contract):
    policy_rule_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    applicability: PolicyApplicability
    decision: PolicyDecision
    event_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    path: CapabilityPath | None = None
    explanation: str = Field(min_length=1)


class AnalysisResult(Contract):
    execution_id: str = Field(min_length=1)
    status: AnalysisStatus
    coverage_status: CoverageStatus
    monitored_scope: list[str] = Field(default_factory=list)
    mismatches: list[EffectMismatch] = Field(default_factory=list)
    graph_nodes: list[GraphNode] = Field(default_factory=list)
    graph_edges: list[GraphEdge] = Field(default_factory=list)
    paths: list[CapabilityPath] = Field(default_factory=list)
    graph_truncated: bool = False
    graph_truncation_reasons: list[str] = Field(default_factory=list)
    policy_evaluations: list[PolicyEvaluation] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    incomplete_reasons: list[str] = Field(default_factory=list)
    assessed_at: datetime

    @model_validator(mode="after")
    def preserve_execution_and_path_boundaries(self):
        node_by_id = {node.node_id: node for node in self.graph_nodes}
        edge_by_id = {edge.edge_id: edge for edge in self.graph_edges}
        if any(node.execution_id != self.execution_id for node in self.graph_nodes):
            raise ValueError("analysis graph node crosses the execution boundary")
        for edge in self.graph_edges:
            if (edge.execution_id != self.execution_id or edge.source_node_id not in node_by_id
                    or edge.target_node_id not in node_by_id):
                raise ValueError("analysis graph edge is unresolved or crosses the execution boundary")
        for path in self.paths:
            if path.execution_id != self.execution_id:
                raise ValueError("analysis path crosses the execution boundary")
            if any(node_id not in node_by_id for node_id in path.node_ids):
                raise ValueError("analysis path contains an unresolved graph node")
            if any(edge_id not in edge_by_id for edge_id in path.edge_ids):
                raise ValueError("analysis path contains an unresolved graph edge")
            expected_event_ids = {event_id for edge_id in path.edge_ids
                                  for event_id in edge_by_id[edge_id].event_ids}
            if (len(path.event_ids) != len(set(path.event_ids))
                    or set(path.event_ids) != expected_event_ids):
                raise ValueError("analysis path event IDs do not match the events on its edges")
            for index, edge_id in enumerate(path.edge_ids):
                edge = edge_by_id[edge_id]
                if (index + 1 >= len(path.node_ids)
                        or edge.source_node_id != path.node_ids[index]
                        or edge.target_node_id != path.node_ids[index + 1]):
                    raise ValueError("analysis path does not follow its recorded directed edges")
            endpoint = node_by_id[path.node_ids[-1]]
            if path.destination_id != (endpoint.resource_id or endpoint.node_id):
                raise ValueError("analysis path destination does not match its endpoint node")
        if any(item.execution_id != self.execution_id for item in self.mismatches):
            raise ValueError("analysis mismatch crosses the execution boundary")
        if any(item.execution_id != self.execution_id for item in self.findings):
            raise ValueError("analysis finding crosses the execution boundary")
        if any(item.path is not None and item.path not in self.paths for item in self.findings):
            raise ValueError("analysis finding references a path outside the result graph")
        if any(item.path is not None and item.path.execution_id != self.execution_id
               for item in self.policy_evaluations):
            raise ValueError("policy evaluation path crosses the execution boundary")
        if any(item.path is not None and item.path not in self.paths for item in self.policy_evaluations):
            raise ValueError("policy evaluation references a path outside the result graph")
        if self.graph_truncated != bool(self.graph_truncation_reasons):
            raise ValueError("graph truncation flag and reasons must be consistent")
        if self.graph_truncated and not set(self.graph_truncation_reasons).issubset(self.incomplete_reasons):
            raise ValueError("graph truncation reasons must be recorded as incomplete analysis reasons")
        if any(set(item.path.event_ids) - set(item.event_ids)
               for item in self.policy_evaluations if item.path is not None):
            raise ValueError("policy evaluation omits event IDs from its evidence-backed path")
        if any(set(item.evidence_ids) != {ref.evidence_id for ref in item.evidence_references}
               for item in self.findings):
            raise ValueError("finding evidence IDs do not match its resolvable references")
        if self.status == AnalysisStatus.NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE:
            if (self.coverage_status != CoverageStatus.COMPLETE or self.incomplete_reasons
                    or self.graph_truncated):
                raise ValueError("a no-violation conclusion requires complete, gap-free analysis")
        if self.status == AnalysisStatus.CONFIRMED_VIOLATION and not any(
                item.assessment == Assessment.CONFIRMED_VIOLATION for item in self.findings):
            raise ValueError("confirmed analysis status requires a confirmed finding")
        if self.status == AnalysisStatus.POTENTIAL_RISK and not any(
                item.assessment == Assessment.POTENTIAL_RISK for item in self.findings):
            raise ValueError("potential-risk analysis status requires a potential-risk finding")
        return self
