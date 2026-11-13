"""Small, deterministic R1 domain contracts; not application workflows."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EffectType(StrEnum):
    READS = "READS"
    SEARCHES = "SEARCHES"
    TRANSFORMS = "TRANSFORMS"
    CREATES = "CREATES"
    WRITES = "WRITES"
    TRANSMITS = "TRANSMITS"
    DELEGATES = "DELEGATES"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class GraphEdgeType(StrEnum):
    """Relationship labels between graph resources; not observed operations."""
    READS = "READS"
    SEARCHES = "SEARCHES"
    TRANSFORMS = "TRANSFORMS"
    USES = "USES"
    CREATES = "CREATES"
    WRITES = "WRITES"
    TRANSMITS = "TRANSMITS"
    DELEGATES = "DELEGATES"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class Classification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


CLASSIFICATION_RANK = {item: rank for rank, item in enumerate(Classification)}


def highest_classification(*labels: Classification) -> Classification:
    """Conservative join: transformed data inherits the most sensitive input."""
    if not labels:
        raise ValueError("At least one input classification is required")
    return max(labels, key=CLASSIFICATION_RANK.__getitem__)


class CoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class Assessment(StrEnum):
    CONFIRMED_VIOLATION = "CONFIRMED_VIOLATION"
    POTENTIAL_RISK = "POTENTIAL_RISK"
    EFFECT_MISMATCH = "EFFECT_MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    NO_VIOLATION_OBSERVED = "NO_VIOLATION_OBSERVED"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class EvidenceReference(Contract):
    evidence_id: str = Field(min_length=1)
    kind: str = Field(min_length=1, description="Recorder, fixture, or immutable artifact type")
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    uri: str | None = None
    recorded_at: datetime
    llm_generated: bool = False

    @model_validator(mode="after")
    def reject_llm_as_evidence(self):
        if self.llm_generated:
            raise ValueError("LLM-generated content cannot be authoritative evidence")
        return self


class ToolManifest(Contract):
    tool_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$")
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    declared_capabilities: list[str]
    declared_effects: list[EffectType]
    optional_effects: list[EffectType] = Field(default_factory=list)
    permission_scope: list[str]
    allowed_resources: list[str] = []
    allowed_destinations: list[str] = []
    status: str = "ACTIVE"

    @model_validator(mode="after")
    def optional_effects_must_be_declared(self):
        if not set(self.optional_effects).issubset(self.declared_effects):
            raise ValueError("Optional effects must be a subset of declared effects")
        return self


class CoverageRecord(Contract):
    coverage_id: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    status: CoverageStatus
    monitored_scope: list[str]
    monitored_operations: list[str] = []
    gaps: list[str] = []
    recorder_version: str = Field(min_length=1)
    assessed_at: datetime
    evidence_ids: list[str] = []

    @model_validator(mode="after")
    def constrain_complete_scope(self):
        if self.status == CoverageStatus.COMPLETE and (not self.monitored_scope or self.gaps):
            raise ValueError("COMPLETE requires an explicit non-empty scope and no known gaps within it")
        return self


class ObservedEffect(Contract):
    event_id: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    invocation_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    occurred_at: datetime
    effect_type: EffectType
    source_resource: str | None = None
    destination_resource: str | None = None
    classification: Classification
    operation: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(min_length=1)
    metadata: dict[str, Any] = {}


class GraphNode(Contract):
    node_id: str = Field(min_length=1)
    node_type: str = Field(pattern=r"^(TOOL|ASSET|TRANSFORMATION|DESTINATION|POLICY|EXECUTION)$")
    resource_id: str | None = None
    execution_id: str | None = None
    classification: Classification | None = None


class GraphEdge(Contract):
    edge_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    edge_type: GraphEdgeType
    execution_id: str = Field(min_length=1)
    event_ids: list[str] = Field(min_length=1)
    classification: Classification
    evidence_ids: list[str] = Field(min_length=1)
    invocation_ids: list[str] = Field(default_factory=list)


class CapabilityPath(Contract):
    execution_id: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=2)
    edge_ids: list[str] = Field(min_length=1)
    event_ids: list[str] = Field(min_length=1)
    source_classification: Classification
    destination_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def connected_shape(self):
        if len(self.node_ids) != len(self.edge_ids) + 1:
            raise ValueError("Path node count must be edge count plus one")
        return self


class PolicyKind(StrEnum):
    CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION = "CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION"
    RESTRICT_ASSET_ACCESS = "RESTRICT_ASSET_ACCESS"
    RESTRICT_WRITE_DESTINATION = "RESTRICT_WRITE_DESTINATION"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    PROHIBIT_DESTINATION = "PROHIBIT_DESTINATION"


class PolicyRule(Contract):
    rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: PolicyKind
    scope: dict[str, Any]
    conditions: dict[str, Any]
    outcome: str = "DENY"
    effective_from: datetime
    effective_to: datetime | None = None
    evidence_requirements: list[str] = Field(min_length=1)
    active: bool = True


class Finding(Contract):
    finding_id: str = Field(min_length=1)
    finding_type: str = Field(min_length=1)
    assessment: Assessment
    severity: Severity
    execution_id: str = Field(min_length=1)
    tool_ids: list[str]
    event_ids: list[str]
    policy_rule_id: str | None = None
    path: CapabilityPath | None = None
    uncertainty: list[str] = []
    coverage_status: CoverageStatus
    status: str = "OPEN"
    summary: str = ""
    invocation_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    policy_version: str | None = None
    severity_rationale: str = ""
    next_investigative_action: str = ""

    @model_validator(mode="after")
    def violation_requires_evidence_and_policy(self):
        if self.assessment == Assessment.CONFIRMED_VIOLATION:
            if not self.policy_rule_id or not self.event_ids or self.path is None:
                raise ValueError("Confirmed violation requires policy, event provenance, and a path")
        return self


class RemediationType(StrEnum):
    RESTRICT_DESTINATION = "RESTRICT_DESTINATION"
    RESTRICT_ASSET = "RESTRICT_ASSET"
    RESTRICT_OPERATION = "RESTRICT_OPERATION"
    FILTER_FIELDS = "FILTER_FIELDS"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    ADD_VALIDATION = "ADD_VALIDATION"
    BLOCK_EFFECT = "BLOCK_EFFECT"


class RemediationCandidate(Contract):
    remediation_id: str = Field(min_length=1)
    finding_id: str = Field(min_length=1)
    control_type: RemediationType
    target: str = Field(min_length=1)
    blocked_path: list[str] = Field(min_length=1)
    benign_scenarios_to_preserve: list[str]
    rationale: str = Field(min_length=1)
    verification_criteria: list[str] = Field(min_length=1)
    status: str = "PROPOSED"
    verification_run_ids: list[str] = []

    @model_validator(mode="after")
    def cannot_claim_verified_without_run(self):
        if self.status == "VERIFIED" and not self.verification_run_ids:
            raise ValueError("A remediation cannot be VERIFIED without a verification run")
        return self


class VerificationOutcome(StrEnum):
    DANGEROUS_BLOCKED = "DANGEROUS_BLOCKED"
    LEGITIMATE_PRESERVED = "LEGITIMATE_PRESERVED"
    ALTERNATIVE_PATH_FOUND = "ALTERNATIVE_PATH_FOUND"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class VerificationRun(Contract):
    verification_run_id: str = Field(min_length=1)
    remediation_id: str = Field(min_length=1)
    execution_ids: list[str] = Field(min_length=1)
    outcomes: list[VerificationOutcome] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    completed_at: datetime


def assess_absence_of_violation(coverage: CoverageStatus, policy_violation_demonstrated: bool) -> Assessment:
    """The positive flag means a policy violation is already evidence-demonstrated, not merely an effect."""
    if policy_violation_demonstrated:
        return Assessment.CONFIRMED_VIOLATION
    if coverage != CoverageStatus.COMPLETE:
        return Assessment.INCONCLUSIVE
    return Assessment.NO_VIOLATION_OBSERVED


def can_confirm_policy_violation(path: CapabilityPath | None, rule: PolicyRule | None,
                                 condition_demonstrated: bool) -> bool:
    """Positive violation requires an actual event-backed path and active applicable rule."""
    return bool(path and path.event_ids and rule and rule.active and condition_demonstrated)
