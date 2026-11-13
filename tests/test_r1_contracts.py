import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.core.schemas.contracts import (
    Assessment, CapabilityPath, Classification, CoverageStatus, EffectType,
    CoverageRecord, EvidenceReference, Finding, ObservedEffect, PolicyKind, PolicyRule,
    RemediationCandidate, RemediationType, Severity, ToolManifest,
    assess_absence_of_violation, can_confirm_policy_violation, highest_classification,
)

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def evidence():
    return EvidenceReference(evidence_id="ev-1", kind="fixture", recorded_at=NOW)


def path():
    return CapabilityPath(execution_id="run-1", node_ids=["asset:doc", "tool:reader", "dest:outside"],
                          edge_ids=["edge-1", "edge-2"], event_ids=["event-1", "event-2"],
                          source_classification=Classification.CONFIDENTIAL,
                          destination_id="dest:outside")


def policy():
    return PolicyRule(rule_id="POL-1", version="1", kind=PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION,
                      scope={"destination_class": "EXTERNAL"}, conditions={"authorized": False},
                      effective_from=NOW, evidence_requirements=["event_path"])


class R1ContractTests(unittest.TestCase):
    def test_valid_tool_manifest_is_accepted(self):
        item = ToolManifest(tool_id="document.reader", name="Reader", version="1.0", description="Reads fixtures",
                            input_schema={"type": "object"}, output_schema={"type": "object"},
                            declared_capabilities=["read_document"], declared_effects=[EffectType.READS],
                            permission_scope=["asset:docs"], allowed_resources=["asset:docs"])
        self.assertEqual(item.tool_id, "document.reader")

    def test_invalid_tool_manifest_is_rejected(self):
        with self.assertRaises(ValidationError):
            ToolManifest(tool_id="bad id", name="", version="1", description="x", input_schema={},
                         output_schema={}, declared_capabilities=[], declared_effects=[], permission_scope=[])

    def test_observed_effect_retains_execution_provenance(self):
        event = ObservedEffect(event_id="event-1", execution_id="run-1", invocation_id="invoke-1",
                               tool_id="reader", sequence=1, occurred_at=NOW, effect_type=EffectType.READS,
                               source_resource="asset:doc", classification=Classification.CONFIDENTIAL,
                               operation="read", outcome="SUCCESS", evidence=[evidence()])
        self.assertEqual((event.execution_id, event.invocation_id, event.tool_id), ("run-1", "invoke-1", "reader"))

    def test_undeclared_observed_effect_is_representable(self):
        manifest = ToolManifest(tool_id="writer", name="Writer", version="1", description="fixture",
                                input_schema={}, output_schema={}, declared_capabilities=[], declared_effects=[],
                                permission_scope=[])
        event = ObservedEffect(event_id="event-x", execution_id="run-x", invocation_id="inv-x", tool_id="writer",
                               sequence=1, occurred_at=NOW, effect_type=EffectType.TRANSMITS,
                               destination_resource="sink:simulated", classification=Classification.INTERNAL,
                               operation="send", outcome="SUCCESS", evidence=[evidence()])
        self.assertNotIn(event.effect_type, manifest.declared_effects)

    def test_event_without_identity_fields_is_rejected(self):
        with self.assertRaises(ValidationError):
            ObservedEffect(event_id="", execution_id="run", invocation_id="invoke", tool_id="t", sequence=1,
                           occurred_at=NOW, effect_type=EffectType.READS, classification=Classification.PUBLIC,
                           operation="read", outcome="SUCCESS", evidence=[evidence()])

    def test_classification_propagates_to_most_sensitive_input(self):
        self.assertEqual(highest_classification(Classification.PUBLIC, Classification.CONFIDENTIAL),
                         Classification.CONFIDENTIAL)
        self.assertEqual(highest_classification(Classification.INTERNAL, Classification.RESTRICTED),
                         Classification.RESTRICTED)

    def test_confidential_unauthorized_destination_path_is_representable(self):
        p = path()
        self.assertEqual(p.source_classification, Classification.CONFIDENTIAL)
        self.assertEqual(p.destination_id, "dest:outside")
        self.assertTrue(p.event_ids)

    def test_partial_trace_is_not_proven_safe(self):
        self.assertEqual(assess_absence_of_violation(CoverageStatus.PARTIAL, False), Assessment.INCONCLUSIVE)
        self.assertEqual(assess_absence_of_violation(CoverageStatus.FAILED, False), Assessment.INCONCLUSIVE)
        self.assertEqual(assess_absence_of_violation(CoverageStatus.UNKNOWN, False), Assessment.INCONCLUSIVE)
        self.assertEqual(assess_absence_of_violation(CoverageStatus.COMPLETE, False), Assessment.NO_VIOLATION_OBSERVED)

    def test_complete_coverage_requires_explicit_gap_free_scope(self):
        with self.assertRaises(ValidationError):
            CoverageRecord(coverage_id="cov", execution_id="run", status=CoverageStatus.COMPLETE,
                           monitored_scope=[], recorder_version="1", assessed_at=NOW)
        with self.assertRaises(ValidationError):
            CoverageRecord(coverage_id="cov", execution_id="run", status=CoverageStatus.COMPLETE,
                           monitored_scope=["synthetic-tool-io"], gaps=["resource not instrumented"],
                           recorder_version="1", assessed_at=NOW)

    def test_violation_requires_traceable_path_and_applicable_policy(self):
        self.assertTrue(can_confirm_policy_violation(path(), policy(), True))
        self.assertFalse(can_confirm_policy_violation(None, policy(), True))
        self.assertFalse(can_confirm_policy_violation(path(), None, True))
        self.assertFalse(can_confirm_policy_violation(path(), policy(), False))
        with self.assertRaises(ValidationError):
            Finding(finding_id="f", finding_type="POLICY", assessment=Assessment.CONFIRMED_VIOLATION,
                    severity=Severity.HIGH, execution_id="run-1", tool_ids=["reader"], event_ids=[],
                    policy_rule_id=None, coverage_status=CoverageStatus.PARTIAL)

    def test_remediation_cannot_be_verified_without_verification_evidence(self):
        with self.assertRaises(ValidationError):
            RemediationCandidate(remediation_id="fix", finding_id="f", control_type=RemediationType.RESTRICT_DESTINATION,
                                 target="sink:outside", blocked_path=["event-1"], benign_scenarios_to_preserve=["internal"],
                                 rationale="block egress", verification_criteria=["danger blocked"], status="VERIFIED")
        accepted = RemediationCandidate(remediation_id="fix", finding_id="f", control_type=RemediationType.RESTRICT_DESTINATION,
                                        target="sink:outside", blocked_path=["event-1"], benign_scenarios_to_preserve=["internal"],
                                        rationale="block egress", verification_criteria=["danger blocked"], status="PROPOSED")
        self.assertEqual(accepted.status, "PROPOSED")

    def test_llm_explanation_cannot_become_evidence(self):
        with self.assertRaises(ValidationError):
            EvidenceReference(evidence_id="llm", kind="explanation", recorded_at=NOW, llm_generated=True)


if __name__ == "__main__":
    unittest.main()
