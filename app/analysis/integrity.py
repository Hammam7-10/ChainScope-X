"""R2 report/evidence integrity checks; hashes alone are never treated as execution proof."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timezone
from typing import Any

from app.core.schemas.contracts import ObservedEffect


@dataclass(frozen=True)
class IntegrityAudit:
    events: tuple[ObservedEffect, ...]
    issues: tuple[str, ...]


def _event_facts_match(payload: dict[str, Any], event: ObservedEffect) -> bool:
    expected = {
        "event_id": event.event_id,
        "execution_id": event.execution_id,
        "invocation_id": event.invocation_id,
        "tool_id": event.tool_id,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat(),
        "effect_type": event.effect_type.value,
        "source_resource": event.source_resource,
        "destination_resource": event.destination_resource,
        "classification": event.classification.value,
        "operation": event.operation,
        "outcome": event.outcome,
        "metadata": event.metadata,
    }
    return all(payload.get(key) == value for key, value in expected.items())


def audit_execution_report(report: Any, evidence_store: Any) -> IntegrityAudit:
    """Accept only traceable R2 records; return safe issue codes, never exception text."""
    issues: list[str] = []
    execution = report.execution
    execution_id = execution.execution_id
    coverage = report.coverage

    if coverage.execution_id != execution_id:
        issues.append("coverage_execution_mismatch")
    if coverage.status.value == "COMPLETE" and (not coverage.monitored_scope or coverage.gaps):
        issues.append("invalid_complete_coverage_claim")

    invocation_by_id: dict[str, Any] = {}
    ambiguous_invocation_ids: set[str] = set()
    for invocation in report.invocations:
        if invocation.invocation_id in invocation_by_id:
            issues.append("duplicate_invocation_id")
            ambiguous_invocation_ids.add(invocation.invocation_id)
            continue
        invocation_by_id[invocation.invocation_id] = invocation
        if invocation.execution_id != execution_id:
            issues.append("invocation_execution_mismatch")
        if invocation.status not in {"SUCCEEDED", "FAILED"}:
            issues.append("invocation_not_terminal")

    accepted_events: list[ObservedEffect] = []
    event_by_id: dict[str, ObservedEffect] = {}
    all_event_evidence_ids: set[str] = set()
    for event in report.events:
        if not isinstance(event, ObservedEffect):
            issues.append("unrecognized_event_record")
            continue
        prior = event_by_id.get(event.event_id)
        if prior is not None:
            if prior.model_dump(mode="json") != event.model_dump(mode="json"):
                issues.append("conflicting_duplicate_event")
            else:
                issues.append("duplicate_event_deduplicated")
            continue
        event_by_id[event.event_id] = event
        invocation = invocation_by_id.get(event.invocation_id)
        valid = True
        if event.invocation_id in ambiguous_invocation_ids:
            issues.append("event_invocation_identity_ambiguous")
            valid = False
        if event.execution_id != execution_id:
            issues.append("event_execution_mismatch")
            valid = False
        if invocation is None:
            issues.append("event_invocation_missing")
            valid = False
        elif invocation.tool_id != event.tool_id or invocation.execution_id != event.execution_id:
            issues.append("event_invocation_identity_mismatch")
            valid = False
        if event.outcome not in {"SUCCESS", "FAILED"}:
            issues.append("event_outcome_unrecognized")
            valid = False
        if event.occurred_at.tzinfo is None or event.occurred_at.utcoffset() is None:
            issues.append("event_timestamp_not_timezone_aware")
            valid = False
        if not event.evidence:
            issues.append("event_evidence_missing")
            valid = False
        for reference in event.evidence:
            all_event_evidence_ids.add(reference.evidence_id)
            try:
                record = evidence_store.resolve(reference.evidence_id)
                if (reference.llm_generated or not evidence_store.verify(reference)
                        or record.kind != "observed_effect"
                        or not _event_facts_match(record.payload(), event)):
                    issues.append("event_evidence_does_not_resolve_to_event")
                    valid = False
            except Exception:
                issues.append("event_evidence_unavailable")
                valid = False
        if valid:
            accepted_events.append(event)

    expected_sequences = list(range(1, len(report.events) + 1))
    actual_sequences = sorted(event.sequence for event in report.events
                              if isinstance(event, ObservedEffect))
    if actual_sequences != expected_sequences:
        issues.append("event_sequence_incomplete_or_duplicate")

    coverage_ids = set(coverage.evidence_ids)
    if not all_event_evidence_ids.issubset(coverage_ids):
        issues.append("coverage_omits_event_evidence")
    for evidence_id in sorted(coverage_ids):
        try:
            record = evidence_store.resolve(evidence_id)
            digest = hashlib.sha256(record.canonical_payload.encode("utf-8")).hexdigest()
            if digest != record.sha256:
                issues.append("coverage_evidence_integrity_failure")
            if record.kind == "observed_effect" and evidence_id not in all_event_evidence_ids:
                issues.append("observed_event_evidence_missing_from_report")
        except Exception:
            issues.append("coverage_evidence_unavailable")

    self_check = execution.self_check
    if coverage.status.value == "COMPLETE":
        if self_check is None:
            issues.append("complete_coverage_without_self_check")
        else:
            try:
                record = evidence_store.resolve(self_check.evidence_id)
                if (not evidence_store.verify(self_check) or record.kind != "recorder_self_check"
                        or record.payload().get("execution_id") != execution_id
                        or not record.payload().get("active")):
                    issues.append("recorder_self_check_invalid")
                if self_check.evidence_id not in coverage_ids:
                    issues.append("coverage_omits_self_check")
            except Exception:
                issues.append("recorder_self_check_unavailable")

    return IntegrityAudit(tuple(sorted(accepted_events, key=lambda item: item.sequence)),
                          tuple(dict.fromkeys(issues)))
