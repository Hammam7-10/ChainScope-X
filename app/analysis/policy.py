"""Small deterministic evaluator for the structured R1 policy rules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.analysis.models import (
    PolicyApplicability, PolicyDecision, PolicyEvaluation,
)
from app.core.schemas.contracts import (
    CapabilityPath, Classification, CoverageStatus, EffectType, GraphEdge,
    GraphNode, ObservedEffect, PolicyKind, PolicyRule,
)


_SCOPE_KEYS = {"execution_ids", "tool_ids", "resource_ids", "destination_ids",
               "effect_types", "classifications"}
_ALLOWED_CONDITION_KEYS = {
    PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION: {
        "authorized_destinations", "maximum_classification"},
    PolicyKind.RESTRICT_ASSET_ACCESS: {"allowed_resources"},
    PolicyKind.RESTRICT_WRITE_DESTINATION: {
        "allowed_resources", "prohibited_resources", "prohibited_destinations"},
    PolicyKind.APPROVAL_REQUIRED: {"effect_types"},
    PolicyKind.PROHIBIT_DESTINATION: {"prohibited_destinations"},
}


@dataclass(frozen=True)
class PolicyEvaluationResult:
    evaluations: tuple[PolicyEvaluation, ...]
    issues: tuple[str, ...]


class PolicyEvaluator:
    def evaluate(self, policies: Iterable[PolicyRule], *, execution, coverage,
                 events: Iterable[ObservedEffect], nodes: Iterable[GraphNode],
                 edges: Iterable[GraphEdge], paths: Iterable[CapabilityPath],
                 integrity_complete: bool = True) -> PolicyEvaluationResult:
        event_by_id = {event.event_id: event for event in events}
        node_by_id = {node.node_id: node for node in nodes}
        edge_by_id = {edge.edge_id: edge for edge in edges}
        path_list = tuple(paths)
        evaluations: list[PolicyEvaluation] = []
        issues: list[str] = []
        evaluated_at = execution.ended_at or execution.started_at
        policy_list = tuple(policies)
        policy_counts: dict[tuple[str, str], int] = {}
        for rule in policy_list:
            key = (rule.rule_id, rule.version)
            policy_counts[key] = policy_counts.get(key, 0) + 1

        for rule in sorted(policy_list, key=lambda item: (item.rule_id, item.version)):
            if policy_counts[(rule.rule_id, rule.version)] > 1:
                evaluations.append(self._not_applicable(
                    rule, PolicyApplicability.UNSUPPORTED_RULE,
                    "Duplicate policy ID/version entries are ambiguous and were not applied."))
                issues.append("duplicate_policy_identity")
                continue
            inactive_state = self._temporal_status(rule, evaluated_at)
            if inactive_state is not None:
                evaluations.append(self._not_applicable(rule, inactive_state,
                    f"Policy {inactive_state.value.lower().replace('_', ' ')} at the execution time."))
                continue
            invalid_reason = self._invalid_rule_reason(rule)
            if invalid_reason:
                evaluations.append(self._not_applicable(rule, PolicyApplicability.UNSUPPORTED_RULE,
                                                         invalid_reason))
                issues.append("unsupported_policy_rule")
                continue

            candidates = self._candidate_paths(rule, path_list, event_by_id, node_by_id)
            scoped = [(path, path_events) for path, path_events in candidates
                      if self._scope_matches(rule, path, path_events, node_by_id)]
            scoped = self._deduplicate_scoped_paths(rule, scoped)
            if not scoped:
                evaluations.append(self._not_applicable(
                    rule, PolicyApplicability.OUT_OF_SCOPE,
                    "No evidence-backed path or event matches this rule's explicit applicability scope."))
                continue

            for path, path_events in scoped:
                if rule.kind in {PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION,
                                 PolicyKind.PROHIBIT_DESTINATION}:
                    target_types = {EffectType.TRANSMITS}
                elif rule.kind == PolicyKind.RESTRICT_ASSET_ACCESS:
                    target_types = {EffectType.READS, EffectType.SEARCHES}
                elif rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION:
                    target_types = {EffectType.CREATES, EffectType.WRITES}
                else:
                    target_types = {EffectType(item) for item in rule.conditions.get("effect_types", [])}
                target_invocations = {event.invocation_id for event in path_events
                                      if event.effect_type in target_types and event.outcome == "SUCCESS"}
                needs_approval_records = (rule.kind == PolicyKind.APPROVAL_REQUIRED
                                          or "approval_event" in rule.evidence_requirements
                                          or rule.outcome == "REQUIRE_APPROVAL")
                approval_events = sorted((event for event in event_by_id.values()
                                          if needs_approval_records
                                          and event.effect_type == EffectType.REQUIRES_APPROVAL
                                          and event.invocation_id in target_invocations),
                                         key=lambda event: (event.sequence, event.event_id))
                evaluation_events = list({event.event_id: event for event in
                                          (*path_events, *approval_events)}.values())
                decision, explanation = self._decide(rule, path, evaluation_events, coverage)
                related_edges = [edge_by_id[item] for item in path.edge_ids if item in edge_by_id]
                evidence_set = {eid for edge in related_edges for eid in edge.evidence_ids}
                evidence_set.update(reference.evidence_id for event in approval_events
                                    for reference in event.evidence)
                if "coverage" in rule.evidence_requirements:
                    evidence_set.update(coverage.evidence_ids)
                evidence_ids = sorted(evidence_set)
                missing_requirements = self._missing_evidence_requirements(
                    rule, path, evaluation_events, coverage, integrity_complete)
                if missing_requirements:
                    decision = PolicyDecision.INCONCLUSIVE
                    explanation = "Required evidence is unavailable: " + ", ".join(missing_requirements) + "."
                event_ids = list(dict.fromkeys([*path.event_ids,
                                                *(event.event_id for event in approval_events)]))
                evaluations.append(PolicyEvaluation(
                    policy_rule_id=rule.rule_id, policy_version=rule.version,
                    applicability=PolicyApplicability.APPLICABLE, decision=decision,
                    event_ids=event_ids, evidence_ids=evidence_ids, path=path,
                    explanation=explanation,
                ))
                if decision == PolicyDecision.INCONCLUSIVE:
                    issues.append("policy_evaluation_inconclusive")

        return PolicyEvaluationResult(tuple(evaluations), tuple(dict.fromkeys(issues)))

    @staticmethod
    def _temporal_status(rule: PolicyRule, at: datetime) -> PolicyApplicability | None:
        if not rule.active:
            return PolicyApplicability.INACTIVE
        if (at.tzinfo is None or at.utcoffset() is None or
                rule.effective_from.tzinfo is None or rule.effective_from.utcoffset() is None or
                (rule.effective_to is not None and
                 (rule.effective_to.tzinfo is None or rule.effective_to.utcoffset() is None))):
            return PolicyApplicability.UNSUPPORTED_RULE
        if rule.effective_to is not None and rule.effective_to < rule.effective_from:
            return PolicyApplicability.UNSUPPORTED_RULE
        if at < rule.effective_from:
            return PolicyApplicability.NOT_YET_EFFECTIVE
        if rule.effective_to is not None and at > rule.effective_to:
            return PolicyApplicability.EXPIRED
        return None

    @staticmethod
    def _invalid_rule_reason(rule: PolicyRule) -> str | None:
        if set(rule.scope) - _SCOPE_KEYS:
            return "Policy contains unsupported scope selectors and was not applied."
        if not rule.scope:
            return "Policy has no explicit applicability scope and was not applied."
        for key, value in rule.scope.items():
            if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
                return "Policy scope selectors must be non-empty lists of stable identifiers."
        if set(rule.conditions) - _ALLOWED_CONDITION_KEYS[rule.kind]:
            return "Policy contains unsupported structured conditions and was not applied."
        if rule.outcome not in {"DENY", "REQUIRE_APPROVAL", "ALLOW"}:
            return "Policy outcome is unsupported and was not applied."
        if rule.kind == PolicyKind.APPROVAL_REQUIRED and rule.outcome == "ALLOW":
            return "APPROVAL_REQUIRED cannot use ALLOW as its expected outcome."
        if set(rule.evidence_requirements) - {"event_path", "observed_event", "coverage", "approval_event"}:
            return "Policy evidence requirement is unsupported and the rule was not applied."
        for key, value in rule.conditions.items():
            if key == "maximum_classification":
                try:
                    Classification(value)
                except (TypeError, ValueError):
                    return "Policy maximum_classification is not a known classification."
            elif key == "effect_types":
                if not isinstance(value, list) or not value:
                    return "Policy effect_types must be a non-empty list."
                try:
                    parsed_effects = [EffectType(item) for item in value]
                except (TypeError, ValueError):
                    return "Policy effect_types contains an unknown effect."
                if (rule.kind == PolicyKind.APPROVAL_REQUIRED
                        and EffectType.REQUIRES_APPROVAL in parsed_effects):
                    return "APPROVAL_REQUIRED must target an operation, not an approval event."
            elif not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                return f"Policy condition {key} must be a list of stable identifiers."
        required = {
            PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION: {"authorized_destinations"},
            PolicyKind.RESTRICT_ASSET_ACCESS: {"allowed_resources"},
            PolicyKind.RESTRICT_WRITE_DESTINATION: set(),
            PolicyKind.APPROVAL_REQUIRED: {"effect_types"},
            PolicyKind.PROHIBIT_DESTINATION: set(),
        }[rule.kind]
        if not required.issubset(rule.conditions):
            return "Policy is missing the structured condition required by its rule kind."
        if rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION and not (
                {"allowed_resources", "prohibited_resources", "prohibited_destinations"} & set(rule.conditions)):
            return "Write restriction requires an explicit allowlist or denylist."
        if rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION and "allowed_resources" not in rule.conditions:
            if not any(rule.conditions.get(key) for key in ("prohibited_resources", "prohibited_destinations")):
                return "Write restriction has an empty denylist and no allowlist; it is ambiguous."
        if rule.kind == PolicyKind.PROHIBIT_DESTINATION:
            if "prohibited_destinations" in rule.conditions and not rule.conditions["prohibited_destinations"]:
                return "Destination prohibition has an empty prohibited set and was not applied."
            if not ("prohibited_destinations" in rule.conditions or "destination_ids" in rule.scope):
                return "Destination prohibition requires explicit prohibited destination identifiers."
        return None

    @staticmethod
    def _missing_evidence_requirements(rule: PolicyRule, path: CapabilityPath,
                                       events: list[ObservedEffect], coverage,
                                       integrity_complete: bool) -> list[str]:
        missing = []
        if "event_path" in rule.evidence_requirements and not (
                path.edge_ids and path.event_ids and len(path.node_ids) >= 2):
            missing.append("event_path")
        if "observed_event" in rule.evidence_requirements and not any(
                event.event_id in path.event_ids and event.evidence for event in events):
            missing.append("observed_event")
        if "coverage" in rule.evidence_requirements and (
                coverage.status != CoverageStatus.COMPLETE or not integrity_complete):
            missing.append("complete_coverage")
        if "approval_event" in rule.evidence_requirements:
            if rule.kind in {PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION,
                             PolicyKind.PROHIBIT_DESTINATION}:
                approval_target_types = {EffectType.TRANSMITS}
            elif rule.kind == PolicyKind.RESTRICT_ASSET_ACCESS:
                approval_target_types = {EffectType.READS, EffectType.SEARCHES}
            elif rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION:
                approval_target_types = {EffectType.CREATES, EffectType.WRITES}
            else:
                approval_target_types = {EffectType(item)
                                         for item in rule.conditions.get("effect_types", [])}
            path_targets = [event for event in events if event.event_id in path.event_ids
                            and event.effect_type in approval_target_types
                            and event.outcome == "SUCCESS"]
            linked_approvals = [event for event in events
                                if event.effect_type == EffectType.REQUIRES_APPROVAL
                                and event.outcome == "SUCCESS" and event.evidence]
            if not any(approval.invocation_id == target.invocation_id
                       and target.event_id in approval.metadata.get("approved_event_ids", [])
                       for approval in linked_approvals for target in path_targets):
                missing.append("approval_event")
        return missing

    @staticmethod
    def _not_applicable(rule: PolicyRule, status: PolicyApplicability,
                        explanation: str) -> PolicyEvaluation:
        return PolicyEvaluation(policy_rule_id=rule.rule_id, policy_version=rule.version,
                                applicability=status, decision=PolicyDecision.NOT_APPLICABLE,
                                explanation=explanation)

    def _candidate_paths(self, rule: PolicyRule, paths: tuple[CapabilityPath, ...],
                         event_by_id: dict[str, ObservedEffect],
                         node_by_id: dict[str, GraphNode]):
        kind = rule.kind
        candidates = []
        for path in paths:
            path_events = [event_by_id[event_id] for event_id in path.event_ids if event_id in event_by_id]
            if path.execution_id != (path_events[0].execution_id if path_events else path.execution_id):
                continue
            relevant = False
            if kind in {PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION,
                        PolicyKind.PROHIBIT_DESTINATION}:
                relevant = (path.destination_id.startswith("destination:") and any(
                    event.effect_type == EffectType.TRANSMITS and event.outcome == "SUCCESS"
                    and event.destination_resource == path.destination_id for event in path_events))
            elif kind == PolicyKind.RESTRICT_ASSET_ACCESS:
                relevant = any(event.effect_type in {EffectType.READS, EffectType.SEARCHES}
                               and event.outcome == "SUCCESS" and event.source_resource for event in path_events)
            elif kind == PolicyKind.RESTRICT_WRITE_DESTINATION:
                relevant = any(event.effect_type in {EffectType.CREATES, EffectType.WRITES}
                               and event.outcome == "SUCCESS" and event.destination_resource == path.destination_id
                               for event in path_events)
            elif kind == PolicyKind.APPROVAL_REQUIRED:
                effect_types = {EffectType(item) for item in rule.conditions.get("effect_types", [])}
                relevant = any(event.effect_type in effect_types and event.outcome == "SUCCESS"
                               for event in path_events)
            if relevant:
                candidates.append((path, path_events))

        # Keep candidate order stable; policy scope is applied before equivalent event paths are deduplicated.
        candidates.sort(key=lambda item: (
            -self._rank(item[0].source_classification), -len(item[0].node_ids),
            item[0].destination_id, tuple(item[0].event_ids),
            tuple(item[0].node_ids),
        ))
        return candidates

    def _deduplicate_scoped_paths(self, rule: PolicyRule, candidates):
        """Evaluate one strongest, stable graph route per actual policy-target event."""
        by_action: dict[tuple[str, tuple[str, ...]], tuple] = {}
        ordered = sorted(candidates, key=lambda item: (
            -self._rank(item[0].source_classification), -len(item[0].node_ids),
            item[0].destination_id, tuple(item[0].event_ids), tuple(item[0].node_ids),
        ))
        for path, path_events in ordered:
            if rule.kind in {PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION,
                             PolicyKind.PROHIBIT_DESTINATION}:
                effects = {EffectType.TRANSMITS}
            elif rule.kind == PolicyKind.RESTRICT_ASSET_ACCESS:
                effects = {EffectType.READS, EffectType.SEARCHES}
            elif rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION:
                effects = {EffectType.CREATES, EffectType.WRITES}
            else:
                effects = {EffectType(item) for item in rule.conditions.get("effect_types", [])}
            targets = tuple(sorted(event.event_id for event in path_events
                                   if event.effect_type in effects and event.outcome == "SUCCESS"))
            key = (path.destination_id, targets)
            if targets:
                by_action.setdefault(key, (path, path_events))
        return [by_action[key] for key in sorted(by_action)]

    @staticmethod
    def _scope_matches(rule: PolicyRule, path: CapabilityPath,
                       events: list[ObservedEffect], node_by_id: dict[str, GraphNode]) -> bool:
        nodes = [node_by_id[node_id] for node_id in path.node_ids if node_id in node_by_id]
        resource_ids = {node.resource_id for node in nodes if node.resource_id}
        tool_ids = {event.tool_id for event in events if event.tool_id}
        destinations = {path.destination_id}
        effects = {event.effect_type.value for event in events}
        classifications = {event.classification.value for event in events}
        selectors = {
            "execution_ids": {path.execution_id},
            "tool_ids": tool_ids,
            "resource_ids": resource_ids,
            "destination_ids": destinations,
            "effect_types": effects,
            "classifications": classifications,
        }
        return all(set(values) & selectors[key] for key, values in rule.scope.items())

    def _decide(self, rule: PolicyRule, path: CapabilityPath,
                events: list[ObservedEffect], coverage) -> tuple[PolicyDecision, str]:
        destination = path.destination_id
        successful = [event for event in events if event.outcome == "SUCCESS"]
        if rule.kind == PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION:
            authorized = set(rule.conditions.get("authorized_destinations", []))
            max_label = Classification(rule.conditions.get("maximum_classification", "INTERNAL"))
            class_allowed = (self._rank(path.source_classification) <= self._rank(max_label))
            destination_allowed = destination in authorized
            sensitive = self._rank(path.source_classification) >= self._rank(Classification.CONFIDENTIAL)
            if class_allowed and (destination_allowed or not sensitive):
                return PolicyDecision.ALLOW, "The destination is explicitly authorized for this path's classification."
            if rule.outcome == "ALLOW":
                return PolicyDecision.INCONCLUSIVE, "The allow rule does not authorize this destination/classification pair."
            target_event_ids = {event.event_id for event in successful
                                if event.effect_type == EffectType.TRANSMITS
                                and event.destination_resource == destination}
            return self._deny_or_approval(rule, events, coverage,
                "A successful confidential/restricted transmission reached a destination not authorized for its classification.",
                target_event_ids=target_event_ids)

        if rule.kind == PolicyKind.PROHIBIT_DESTINATION:
            prohibited = (set(rule.conditions["prohibited_destinations"])
                          if "prohibited_destinations" in rule.conditions
                          else set(rule.scope.get("destination_ids", [])))
            if destination not in prohibited:
                return PolicyDecision.ALLOW, "The destination is not in this rule's explicit prohibited set."
            return self._deny_or_approval(rule, events, coverage,
                "A successful transmission reached an explicitly prohibited destination.",
                target_event_ids={event.event_id for event in successful
                                  if event.effect_type == EffectType.TRANSMITS
                                  and event.destination_resource == destination})

        if rule.kind == PolicyKind.RESTRICT_ASSET_ACCESS:
            allowed = set(rule.conditions["allowed_resources"])
            relevant = [event for event in successful if event.effect_type in {EffectType.READS, EffectType.SEARCHES}]
            violating = [event for event in relevant if not self._resource_allowed(event.source_resource, allowed)]
            if not violating:
                return PolicyDecision.ALLOW, "Successful access stayed within the policy's explicit resource allowlist."
            return self._deny_or_approval(rule, events, coverage,
                "A successful read/search accessed a resource outside the policy's explicit allowlist.",
                target_event_ids={event.event_id for event in violating})

        if rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION:
            allowed = set(rule.conditions.get("allowed_resources", []))
            prohibited_resources = set(rule.conditions.get("prohibited_resources", []))
            prohibited_destinations = set(rule.conditions.get("prohibited_destinations", []))
            relevant = [event for event in successful if event.effect_type in {EffectType.CREATES, EffectType.WRITES}]
            violating = [event for event in relevant if (
                event.destination_resource in prohibited_resources | prohibited_destinations
                or ("allowed_resources" in rule.conditions and
                    not self._resource_allowed(event.destination_resource, allowed)))]
            if not violating:
                return PolicyDecision.ALLOW, "Successful writes stayed within the explicit policy constraints."
            return self._deny_or_approval(rule, events, coverage,
                "A successful create/write targeted a policy-prohibited resource.",
                target_event_ids={event.event_id for event in violating})

        if rule.kind == PolicyKind.APPROVAL_REQUIRED:
            required_types = {EffectType(item) for item in rule.conditions["effect_types"]}
            target_events = [event for event in successful if event.effect_type in required_types]
            if not target_events:
                return PolicyDecision.ALLOW, "No successful restricted operation matched this approval rule."
            approvals = [event for event in events if event.effect_type == EffectType.REQUIRES_APPROVAL
                         and event.outcome == "SUCCESS"]
            for target in target_events:
                if not any(approval.invocation_id == target.invocation_id and
                           target.event_id in approval.metadata.get("approved_event_ids", [])
                           for approval in approvals):
                    if (coverage.status == CoverageStatus.COMPLETE and
                            "approval-control" in coverage.monitored_scope):
                        return PolicyDecision.DENY, "A successful restricted operation has no linked approval event within complete approval coverage."
                    return PolicyDecision.INCONCLUSIVE, "Approval evidence is absent, but the R2 monitored scope does not establish complete approval coverage."
            return PolicyDecision.ALLOW, "Every successful restricted operation has a linked, successful approval event."

        return PolicyDecision.INCONCLUSIVE, "The policy kind has no supported deterministic evaluator."

    @staticmethod
    def _rank(label: Classification) -> int:
        return list(Classification).index(label)

    @staticmethod
    def _resource_allowed(resource_id: str | None, allowed: set[str]) -> bool:
        if resource_id is None:
            return False
        if resource_id in allowed:
            return True
        return (any(item.startswith("workspace:") for item in allowed)
                and resource_id.startswith(("file:", "stored:", "report:")))

    def _deny_or_approval(self, rule: PolicyRule, events: list[ObservedEffect], coverage,
                          explanation: str, *,
                          target_event_ids: set[str] | None = None) -> tuple[PolicyDecision, str]:
        if rule.outcome == "ALLOW":
            return PolicyDecision.INCONCLUSIVE, "Rule outcome ALLOW conflicts with its prohibited-condition match. " + explanation
        if rule.outcome == "REQUIRE_APPROVAL":
            targets = [event for event in events if event.outcome == "SUCCESS"
                       and ((event.event_id in target_event_ids) if target_event_ids is not None
                            else event.effect_type in {
                                PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION: {EffectType.TRANSMITS},
                                PolicyKind.PROHIBIT_DESTINATION: {EffectType.TRANSMITS},
                                PolicyKind.RESTRICT_ASSET_ACCESS: {EffectType.READS, EffectType.SEARCHES},
                                PolicyKind.RESTRICT_WRITE_DESTINATION: {EffectType.CREATES, EffectType.WRITES},
                                PolicyKind.APPROVAL_REQUIRED: set(),
                            }[rule.kind])]
            approvals = [event for event in events if event.effect_type == EffectType.REQUIRES_APPROVAL
                         and event.outcome == "SUCCESS"]
            if targets and all(any(approval.invocation_id == target.invocation_id and
                                   target.event_id in approval.metadata.get("approved_event_ids", [])
                                   for approval in approvals) for target in targets):
                return PolicyDecision.ALLOW, "The required approval is recorded for the related operation."
            if (coverage.status != CoverageStatus.COMPLETE or
                    "approval-control" not in coverage.monitored_scope):
                return PolicyDecision.INCONCLUSIVE, explanation + " Coverage is incomplete, so approval absence is not proof."
            return PolicyDecision.DENY, explanation + " No linked approval event was found within complete approval coverage."
        return PolicyDecision.DENY, explanation
