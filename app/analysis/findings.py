"""Evidence-linked finding construction with a small explainable severity rubric."""
from __future__ import annotations

import hashlib
from typing import Iterable

from app.analysis.models import (
    AnalysisStatus, EffectMismatch, MismatchCategory, PolicyApplicability,
    PolicyDecision, PolicyEvaluation,
)
from app.core.schemas.contracts import (
    Assessment, Classification, CoverageStatus, EffectType, EvidenceReference, Finding,
    PolicyKind, PolicyRule, Severity, can_confirm_policy_violation,
)


class FindingGenerator:
    def generate(self, *, execution_id: str, coverage, mismatches: Iterable[EffectMismatch],
                 policy_evaluations: Iterable[PolicyEvaluation], policies: Iterable[PolicyRule],
                 events, paths, evidence_store) -> tuple[Finding, ...]:
        events = tuple(events)
        paths = tuple(paths)
        mismatches = tuple(mismatches)
        policy_evaluations = tuple(policy_evaluations)
        policies = tuple(policies)
        event_by_id = {event.event_id: event for event in events}
        policy_by_key = {(rule.rule_id, rule.version): rule for rule in policies}
        finding_by_id: dict[str, Finding] = {}

        def resolve_reference(evidence_id: str):
            try:
                record = evidence_store.resolve(evidence_id)
                reference = EvidenceReference(evidence_id=record.evidence_id, kind=record.kind,
                                              sha256=record.sha256, recorded_at=record.recorded_at)
                return reference if evidence_store.verify(reference) else None
            except Exception:
                return None

        def add(*, finding_type: str, assessment: Assessment, severity: Severity,
                tool_ids: Iterable[str] = (), event_ids: Iterable[str] = (),
                invocation_ids: Iterable[str] = (), evidence_ids: Iterable[str] = (),
                policy_rule_id: str | None = None, policy_version: str | None = None,
                path=None, uncertainty: Iterable[str] = (), summary: str,
                rationale: str, next_action: str) -> None:
            event_ids = list(dict.fromkeys(event_ids))
            invocation_ids = sorted(set(invocation_ids))
            tool_ids = sorted(set(tool_ids))
            evidence_ids = sorted(set(evidence_ids))
            uncertainty = list(uncertainty)
            references = [reference for evidence_id in evidence_ids
                          if (reference := resolve_reference(evidence_id)) is not None]
            references.sort(key=lambda item: item.evidence_id)
            if set(evidence_ids) != {item.evidence_id for item in references} and assessment in {
                    Assessment.EFFECT_MISMATCH, Assessment.CONFIRMED_VIOLATION, Assessment.POTENTIAL_RISK}:
                assessment = Assessment.INCONCLUSIVE
                severity = Severity.INFORMATIONAL
                uncertainty.append("one_or_more_evidence_references_failed_resolution_or_verification")
                rationale = "Evidence could not be fully resolved and verified; no adverse conclusion is asserted."
            material = "|".join((execution_id, finding_type, assessment.value, policy_rule_id or "",
                                 policy_version or "", ",".join(event_ids),
                                 path.destination_id if path else ""))
            finding_id = "finding:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
            finding_by_id.setdefault(finding_id, Finding(
                finding_id=finding_id, finding_type=finding_type, assessment=assessment,
                severity=severity, execution_id=execution_id, tool_ids=tool_ids,
                event_ids=event_ids, policy_rule_id=policy_rule_id, policy_version=policy_version,
                path=path, uncertainty=list(uncertainty), coverage_status=coverage.status,
                summary=summary, invocation_ids=invocation_ids,
                evidence_ids=[item.evidence_id for item in references], evidence_references=references,
                severity_rationale=rationale, next_investigative_action=next_action,
            ))

        for mismatch in mismatches:
            related = [event_by_id[item] for item in mismatch.event_ids if item in event_by_id]
            path = self._path_for_events(paths, mismatch.event_ids)
            severity, rationale = self._mismatch_severity(mismatch.category, related)
            add(
                finding_type=mismatch.category.value, assessment=mismatch.assessment,
                severity=severity, tool_ids=[mismatch.tool_id], event_ids=mismatch.event_ids,
                invocation_ids=mismatch.invocation_ids, evidence_ids=mismatch.evidence_ids,
                path=path, uncertainty=[mismatch.explanation] if mismatch.assessment == Assessment.INCONCLUSIVE else [],
                summary=mismatch.explanation, rationale=rationale,
                next_action=self._mismatch_action(mismatch.category),
            )

        for evaluation in policy_evaluations:
            rule = policy_by_key.get((evaluation.policy_rule_id, evaluation.policy_version))
            related = [event_by_id[item] for item in evaluation.event_ids if item in event_by_id]
            if evaluation.applicability != PolicyApplicability.APPLICABLE:
                add(
                    finding_type="POLICY_NOT_APPLICABLE", assessment=Assessment.INCONCLUSIVE,
                    severity=Severity.INFORMATIONAL, event_ids=evaluation.event_ids,
                    invocation_ids=[event.invocation_id for event in related],
                    evidence_ids=evaluation.evidence_ids, policy_rule_id=evaluation.policy_rule_id,
                    policy_version=evaluation.policy_version, path=evaluation.path,
                    uncertainty=[evaluation.explanation], summary=evaluation.explanation,
                    rationale="No violation is inferred from an inactive, expired, unsupported, or out-of-scope rule.",
                    next_action="Review the policy status, effective dates, and scope before relying on it.",
                )
                continue
            if evaluation.decision == PolicyDecision.ALLOW:
                continue
            if evaluation.decision == PolicyDecision.DENY:
                path_events = ([event_by_id[item] for item in evaluation.path.event_ids if item in event_by_id]
                               if evaluation.path else [])
                evaluation_events = [event_by_id[item] for item in evaluation.event_ids
                                     if item in event_by_id]
                association_valid = bool(rule and self._policy_evidence_is_bound(
                    evaluation, rule, execution_id, paths, path_events, evaluation_events,
                    coverage, evidence_store))
                condition_demonstrated = bool(rule and evaluation.path and association_valid and
                                              self._policy_condition_demonstrated(
                                                  rule, evaluation.path, evaluation_events, coverage))
                confirmed = bool(rule and evaluation.path and condition_demonstrated and
                                 evaluation.applicability == PolicyApplicability.APPLICABLE and
                                 can_confirm_policy_violation(evaluation.path, rule, condition_demonstrated))
                assessment = Assessment.CONFIRMED_VIOLATION if confirmed else Assessment.INCONCLUSIVE
                severity, rationale = self._policy_severity(evaluation.path, evaluation_events, confirmed)
                add(
                    finding_type="POLICY_VIOLATION" if confirmed else "POLICY_EVALUATION_INCOMPLETE",
                    assessment=assessment, severity=severity,
                    tool_ids=[event.tool_id for event in evaluation_events], event_ids=evaluation.event_ids,
                    invocation_ids=[event.invocation_id for event in evaluation_events],
                    evidence_ids=evaluation.evidence_ids, policy_rule_id=evaluation.policy_rule_id,
                    policy_version=evaluation.policy_version, path=evaluation.path,
                    uncertainty=[] if confirmed else [evaluation.explanation],
                    summary=evaluation.explanation, rationale=rationale,
                    next_action="Review the linked event evidence and confirm the rule scope with its policy owner.",
                )
            elif evaluation.decision in {PolicyDecision.INCONCLUSIVE, PolicyDecision.REQUIRE_APPROVAL}:
                positive_events = [event for event in related if event.outcome == "SUCCESS"]
                assessment = Assessment.POTENTIAL_RISK if positive_events else Assessment.INCONCLUSIVE
                add(
                    finding_type="POLICY_REVIEW_REQUIRED", assessment=assessment,
                    severity=Severity.MEDIUM if positive_events else Severity.INFORMATIONAL,
                    tool_ids=[event.tool_id for event in related], event_ids=evaluation.event_ids,
                    invocation_ids=[event.invocation_id for event in related],
                    evidence_ids=evaluation.evidence_ids, policy_rule_id=evaluation.policy_rule_id,
                    policy_version=evaluation.policy_version, path=evaluation.path,
                    uncertainty=[evaluation.explanation], summary=evaluation.explanation,
                    rationale="The rule identifies a concern, but available coverage/evidence does not support a confirmed violation.",
                    next_action="Collect the missing approval or monitoring evidence and re-evaluate the same execution.",
                )

        # Keep one strongest route per actual transmission event; parallel READS/USES edges
        # must not inflate a single event into multiple findings.
        risk_path_by_event = {}
        for path in paths:
            if not path.destination_id.startswith("destination:external:"):
                continue
            related = [event_by_id[item] for item in path.event_ids if item in event_by_id]
            transmissions = [event for event in related if event.effect_type.value == "TRANSMITS"
                             and event.outcome == "SUCCESS" and event.destination_resource == path.destination_id]
            if not transmissions or self._rank(path.source_classification) < self._rank(Classification.CONFIDENTIAL):
                continue
            score = (self._rank(path.source_classification), len(path.node_ids),
                     tuple(path.event_ids), tuple(path.node_ids))
            for event in transmissions:
                current = risk_path_by_event.get(event.event_id)
                if current is None or score > current[0]:
                    risk_path_by_event[event.event_id] = (score, path)

        for _, path in sorted(risk_path_by_event.values(),
                              key=lambda item: (item[1].destination_id, tuple(item[1].event_ids))):
            related = [event_by_id[item] for item in path.event_ids if item in event_by_id]
            transmissions = [event for event in related if event.effect_type.value == "TRANSMITS"
                             and event.outcome == "SUCCESS" and event.destination_resource == path.destination_id]
            addressed_by_policy = any(
                item.applicability == PolicyApplicability.APPLICABLE and item.path is not None
                and item.path.destination_id == path.destination_id
                and any(event.event_id in item.event_ids for event in transmissions)
                for item in policy_evaluations
            )
            if addressed_by_policy:
                continue
            add(
                finding_type="DESTINATION_AUTHORIZATION_UNVERIFIED",
                assessment=Assessment.POTENTIAL_RISK, severity=Severity.MEDIUM,
                tool_ids=[event.tool_id for event in related], event_ids=path.event_ids,
                invocation_ids=[event.invocation_id for event in related],
                evidence_ids=[ref.evidence_id for event in related for ref in event.evidence],
                path=path, uncertainty=["No active applicable rule established whether this destination is authorized for the observed classification."],
                summary="Sensitive data was positively observed at an external simulated destination, but no active applicable policy resolved its authorization.",
                rationale="Sensitive external transmission is a material review concern; lack of an applicable rule is not proof of a policy violation.",
                next_action="Obtain an explicit destination/classification authorization rule and review the linked event evidence.",
            )

        return tuple(sorted(finding_by_id.values(), key=lambda item: item.finding_id))

    @staticmethod
    def _policy_evidence_is_bound(evaluation, rule, execution_id, paths, path_events,
                                  evaluation_events, coverage, evidence_store) -> bool:
        path = evaluation.path
        if (path is None or path not in paths or path.execution_id != execution_id
                or not path.edge_ids or not path.event_ids or len(path.node_ids) < 2):
            return False
        path_event_ids = set(path.event_ids)
        evaluation_event_ids = set(evaluation.event_ids)
        if (len(evaluation.event_ids) != len(evaluation_event_ids)
                or not path_event_ids.issubset(evaluation_event_ids)):
            return False
        if ({event.event_id for event in path_events} != path_event_ids
                or {event.event_id for event in evaluation_events} != evaluation_event_ids
                or any(event.execution_id != execution_id or event.outcome != "SUCCESS"
                       or not event.evidence for event in path_events)):
            return False
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
        extra_events = [event for event in evaluation_events if event.event_id not in path_event_ids]
        if any(event.effect_type != EffectType.REQUIRES_APPROVAL
               or event.invocation_id not in target_invocations
               or event.outcome not in {"SUCCESS", "FAILED"} or not event.evidence
               for event in extra_events):
            return False

        expected_evidence_ids = set()
        for event in evaluation_events:
            for reference in event.evidence:
                try:
                    record = evidence_store.resolve(reference.evidence_id)
                    if (record.kind != "observed_effect" or not evidence_store.verify(reference)):
                        return False
                except Exception:
                    return False
                expected_evidence_ids.add(reference.evidence_id)
        if "coverage" in rule.evidence_requirements:
            if coverage.status != CoverageStatus.COMPLETE:
                return False
            expected_evidence_ids.update(coverage.evidence_ids)
        if (not expected_evidence_ids or len(evaluation.evidence_ids) != len(set(evaluation.evidence_ids))
                or set(evaluation.evidence_ids) != expected_evidence_ids):
            return False
        for evidence_id in expected_evidence_ids:
            if FindingGenerator._resolve_and_verify(evidence_store, evidence_id) is None:
                return False
        return True

    @staticmethod
    def _resolve_and_verify(evidence_store, evidence_id: str):
        try:
            record = evidence_store.resolve(evidence_id)
            reference = EvidenceReference(evidence_id=record.evidence_id, kind=record.kind,
                                          sha256=record.sha256, recorded_at=record.recorded_at)
            return reference if evidence_store.verify(reference) else None
        except Exception:
            return None

    @staticmethod
    def _policy_condition_demonstrated(rule: PolicyRule, path, events, coverage) -> bool:
        successful = [event for event in events if event.outcome == "SUCCESS"]
        if rule.kind == PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION:
            authorized = set(rule.conditions.get("authorized_destinations", []))
            maximum = Classification(rule.conditions.get("maximum_classification", "INTERNAL"))
            over_classification = (FindingGenerator._rank(path.source_classification)
                                   > FindingGenerator._rank(maximum))
            sensitive_unauthorized = (
                FindingGenerator._rank(path.source_classification)
                >= FindingGenerator._rank(Classification.CONFIDENTIAL)
                and path.destination_id not in authorized)
            return (over_classification or sensitive_unauthorized) and any(
                event.effect_type == EffectType.TRANSMITS
                and event.destination_resource == path.destination_id for event in successful)
        if rule.kind == PolicyKind.PROHIBIT_DESTINATION:
            prohibited = (set(rule.conditions["prohibited_destinations"])
                          if "prohibited_destinations" in rule.conditions
                          else set(rule.scope.get("destination_ids", [])))
            return path.destination_id in prohibited and any(
                event.effect_type == EffectType.TRANSMITS
                and event.destination_resource == path.destination_id for event in successful)
        if rule.kind == PolicyKind.RESTRICT_ASSET_ACCESS:
            allowed = set(rule.conditions.get("allowed_resources", []))
            return any(event.effect_type in {EffectType.READS, EffectType.SEARCHES}
                       and not FindingGenerator._resource_allowed(event.source_resource, allowed)
                       for event in successful)
        if rule.kind == PolicyKind.RESTRICT_WRITE_DESTINATION:
            allowed = set(rule.conditions.get("allowed_resources", []))
            prohibited = (set(rule.conditions.get("prohibited_resources", []))
                          | set(rule.conditions.get("prohibited_destinations", [])))
            has_allowlist = "allowed_resources" in rule.conditions
            return any(event.effect_type in {EffectType.CREATES, EffectType.WRITES}
                       and (event.destination_resource in prohibited or
                            (has_allowlist and not FindingGenerator._resource_allowed(
                                event.destination_resource, allowed)))
                       for event in successful)
        if rule.kind == PolicyKind.APPROVAL_REQUIRED:
            types = {EffectType(item) for item in rule.conditions.get("effect_types", [])}
            targets = [event for event in successful if event.effect_type in types]
            if not targets or coverage.status != CoverageStatus.COMPLETE \
                    or "approval-control" not in coverage.monitored_scope:
                return False
            approvals = [event for event in successful if event.effect_type == EffectType.REQUIRES_APPROVAL]
            return any(not any(approval.invocation_id == target.invocation_id and
                               target.event_id in approval.metadata.get("approved_event_ids", [])
                               for approval in approvals) for target in targets)
        return False

    @staticmethod
    def _resource_allowed(resource_id: str | None, allowed: set[str]) -> bool:
        if resource_id is None:
            return False
        if resource_id in allowed:
            return True
        return (any(item.startswith("workspace:") for item in allowed)
                and resource_id.startswith(("file:", "stored:", "report:")))

    @staticmethod
    def _path_for_events(paths, event_ids):
        wanted = set(event_ids)
        candidates = [path for path in paths if wanted and wanted.issubset(path.event_ids)]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (-len(item.node_ids), item.destination_id,
                                                    tuple(item.event_ids)))[0]

    @staticmethod
    def _rank(label: Classification) -> int:
        return list(Classification).index(label)

    def _mismatch_severity(self, category: MismatchCategory, events):
        if category == MismatchCategory.INCOMPLETE_COMPARISON:
            return Severity.INFORMATIONAL, "The comparison is incomplete; no misconduct is inferred from absent evidence."
        sensitive_transmission = any(
            event.effect_type.value == "TRANSMITS" and self._rank(event.classification) >=
            self._rank(Classification.CONFIDENTIAL) for event in events)
        if sensitive_transmission:
            return Severity.MEDIUM, "A sensitive transmission differs from the manifest; policy assessment, if applicable, is reported separately."
        if category == MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED:
            return Severity.LOW, "A required effect was omitted under complete relevant coverage; this is a mismatch, not a policy violation."
        return Severity.LOW, "The event supports a limited-scope declaration or permission discrepancy; no policy violation is implied."

    @staticmethod
    def _mismatch_action(category: MismatchCategory) -> str:
        if category == MismatchCategory.INCOMPLETE_COMPARISON:
            return "Resolve the identified coverage, invocation, or evidence gap before drawing a negative conclusion."
        if category == MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED:
            return "Review whether the declared required effect is accurate for this successful invocation."
        return "Review the manifest declaration, permission scope, and linked event evidence."

    def _policy_severity(self, path, events, confirmed):
        if not confirmed or path is None:
            return Severity.INFORMATIONAL, "Policy applicability or event-backed provenance was insufficient for a confirmed finding."
        external = path.destination_id.startswith("destination:external:")
        sensitive = self._rank(path.source_classification) >= self._rank(Classification.CONFIDENTIAL)
        if external and sensitive:
            return Severity.CRITICAL, "A sensitive classification has a complete event-backed path to an explicitly prohibited or unauthorized external destination."
        if sensitive:
            return Severity.HIGH, "A confirmed policy violation involves confidential or restricted data with a resolving event path."
        return Severity.MEDIUM, "A confirmed policy violation is supported by a resolving event path at lower classification."
