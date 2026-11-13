import socket
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

from app.analysis import AnalysisService
from app.analysis.findings import FindingGenerator
from app.analysis.graph import CapabilityGraphBuilder
from app.analysis.models import AnalysisStatus, MismatchCategory, PolicyApplicability, PolicyDecision
from app.core.schemas.analysis import AnalysisResult
from app.core.schemas.contracts import (
    Assessment, Classification, CoverageStatus, EffectType, GraphEdge,
    GraphEdgeType, PolicyKind, PolicyRule, Severity,
)
from app.sandbox.resources import EXTERNAL_DESTINATION, INTERNAL_DESTINATION
from app.sandbox.runner import LabRunner, default_monitored_scope


EFFECTIVE_FROM = datetime(2020, 1, 1, tzinfo=timezone.utc)


def policy(rule_id="POL-EXT-1", *, active=True, scope=None, conditions=None,
           kind=PolicyKind.CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION,
           outcome="DENY", version="2.1"):
    if scope is None:
        scope = {"destination_ids": [EXTERNAL_DESTINATION]}
    if conditions is None:
        conditions = {"authorized_destinations": [INTERNAL_DESTINATION],
                      "maximum_classification": "INTERNAL"}
    return PolicyRule(
        rule_id=rule_id, version=version, kind=kind, scope=scope,
        conditions=conditions, outcome=outcome, effective_from=EFFECTIVE_FROM,
        evidence_requirements=["event_path", "observed_event"], active=active,
    )


def analyze(lab, report, policies=(), manifests=None):
    return AnalysisService().analyze(
        report, manifests if manifests is not None else lab.registry.list_manifests(),
        policies, lab.evidence_store,
    )


def confidential_external_workflow(lab, execution_id):
    transformed = lab.invoke(execution_id, "data-transformer", {
        "asset_ids": ["asset:confidential:case-7"], "title": "Synthetic restricted report"})
    stored = lab.invoke(execution_id, "workspace-storage", {
        "file_id": transformed["output"]["file_id"]})
    shared = lab.invoke(execution_id, "file-sharing", {
        "file_id": stored["output"]["stored_file_id"],
        "destination_id": EXTERNAL_DESTINATION})
    return transformed, stored, shared


class EndToEndScenarioTests(unittest.TestCase):
    def test_a_safe_internal_workflow_has_only_real_internal_flow(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        transformed = lab.invoke(execution_id, "data-transformer", {
            "asset_ids": ["asset:public:handbook"], "title": "Internal public report"})
        stored = lab.invoke(execution_id, "workspace-storage", {
            "file_id": transformed["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report)

        self.assertEqual(result.status, AnalysisStatus.NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE)
        self.assertFalse(result.mismatches)
        self.assertFalse(any(event.effect_type == EffectType.TRANSMITS for event in report.events))
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION for item in result.findings))
        source = f"{execution_id}::resource::asset:public:handbook"
        self.assertTrue(any(path.node_ids[0] == source and
                            path.destination_id == stored["output"]["stored_file_id"]
                            for path in result.paths))
        edge_types = {edge.edge_type for edge in result.graph_edges}
        self.assertTrue({GraphEdgeType.TRANSFORMS, GraphEdgeType.CREATES,
                         GraphEdgeType.WRITES, GraphEdgeType.USES}.issubset(edge_types))
        event_by_id = {event.event_id: event for event in report.events}
        for edge in result.graph_edges:
            self.assertEqual(edge.execution_id, execution_id)
            self.assertTrue(edge.event_ids)
            for event_id in edge.event_ids:
                event = event_by_id[event_id]
                self.assertEqual(event.execution_id, edge.execution_id)
                self.assertIn(event.invocation_id, edge.invocation_ids)
                self.assertTrue(set(edge.evidence_ids).issubset({ref.evidence_id for ref in event.evidence}))
        for path in result.paths:
            for index, edge_id in enumerate(path.edge_ids):
                edge = next(edge for edge in result.graph_edges if edge.edge_id == edge_id)
                self.assertEqual(edge.source_node_id, path.node_ids[index])
                self.assertEqual(edge.target_node_id, path.node_ids[index + 1])

        # Descriptions are not graph evidence and cannot create or alter edges.
        changed = [item.model_copy(update={"description": "Unrelated narrative claim"})
                   for item in lab.registry.list_manifests()]
        described = analyze(lab, report, manifests=changed)
        self.assertEqual([item.model_dump(mode="json") for item in result.graph_edges],
                         [item.model_dump(mode="json") for item in described.graph_edges])

    def test_b_adversarial_storage_copy_is_undeclared_and_stays_local(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope(),
                                           adversarial_storage_external_copy=True)
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:confidential:case-7", "filename": "synthetic-copy.txt"})
        with patch.object(socket, "socket", side_effect=AssertionError("network socket forbidden")):
            lab.invoke(execution_id, "workspace-storage", {"file_id": created["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report)

        transmission = next(event for event in report.events if event.effect_type == EffectType.TRANSMITS)
        self.assertEqual(transmission.destination_resource, EXTERNAL_DESTINATION)
        self.assertIn(transmission.event_id, {event_id for mismatch in result.mismatches
                                              for event_id in mismatch.event_ids})
        undeclared = next(item for item in result.mismatches
                          if item.category == MismatchCategory.UNDECLARED_OBSERVED_EFFECT
                          and transmission.event_id in item.event_ids)
        self.assertIn(transmission.source_resource, undeclared.resource_ids)
        self.assertIn(transmission.destination_resource, undeclared.resource_ids)
        categories = {item.category for item in result.mismatches}
        self.assertIn(MismatchCategory.UNDECLARED_OBSERVED_EFFECT, categories)
        self.assertIn(MismatchCategory.UNEXPECTED_OPERATION, categories)
        self.assertIn(MismatchCategory.UNEXPECTED_RESOURCE_OR_DESTINATION, categories)
        self.assertEqual(len(lab.destinations.deliveries(EXTERNAL_DESTINATION)), 1)
        self.assertEqual(result.coverage_status, CoverageStatus.COMPLETE)
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION for item in result.findings))
        # The sensitive external path is a review risk, not an assumed or confirmed policy breach.
        self.assertEqual(result.status, AnalysisStatus.POTENTIAL_RISK)
        self.assertEqual(sum(item.finding_type == "DESTINATION_AUTHORIZATION_UNVERIFIED"
                             for item in result.findings), 1)

    def test_c_confidential_composed_path_matches_active_prohibition(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        confidential_external_workflow(lab, execution_id)
        report = lab.finish_execution(execution_id)
        active_rule = policy()
        result = analyze(lab, report, [active_rule])

        self.assertEqual(result.status, AnalysisStatus.CONFIRMED_VIOLATION)
        evaluation = next(item for item in result.policy_evaluations
                          if item.policy_rule_id == active_rule.rule_id)
        self.assertEqual(evaluation.applicability, PolicyApplicability.APPLICABLE)
        self.assertEqual(evaluation.decision, PolicyDecision.DENY)
        finding = next(item for item in result.findings
                       if item.assessment == Assessment.CONFIRMED_VIOLATION)
        self.assertEqual((finding.policy_rule_id, finding.policy_version),
                         (active_rule.rule_id, active_rule.version))
        self.assertEqual(finding.severity, Severity.CRITICAL)
        self.assertEqual(finding.path.source_classification, Classification.CONFIDENTIAL)
        self.assertIn("asset:confidential:case-7", {
            node.resource_id for node in result.graph_nodes if node.node_type == "ASSET"})
        resource_nodes = {node.resource_id: node for node in result.graph_nodes
                          if node.node_type in {"ASSET", "TRANSFORMATION"}}
        for event in report.events:
            if event.effect_type in {EffectType.TRANSFORMS, EffectType.CREATES, EffectType.WRITES}:
                if event.destination_resource in resource_nodes:
                    self.assertEqual(resource_nodes[event.destination_resource].classification,
                                     Classification.CONFIDENTIAL)
        self.assertEqual(finding.path.destination_id, EXTERNAL_DESTINATION)
        self.assertIn("asset:confidential:case-7", {
            node_id.split("::resource::", 1)[-1] for node_id in finding.path.node_ids
            if "::resource::" in node_id})
        self.assertTrue({"data-transformer", "workspace-storage", "file-sharing"}.issubset(
            {next(node.resource_id for node in result.graph_nodes if node.node_id == node_id)
             for node_id in finding.path.node_ids
             if next(node for node in result.graph_nodes if node.node_id == node_id).node_type == "TOOL"}))
        self.assertTrue(finding.event_ids)
        self.assertTrue(finding.invocation_ids)
        self.assertTrue(finding.evidence_references)
        for reference in finding.evidence_references:
            self.assertTrue(lab.evidence_store.verify(reference))
        self.assertTrue(set(finding.event_ids).issubset({event.event_id for event in report.events}))

    def test_d_partial_and_unknown_coverage_never_report_safe(self):
        active_rule = policy()
        for coverage_mode in ("partial", "unknown"):
            with self.subTest(coverage_mode=coverage_mode):
                lab = LabRunner()
                scope = default_monitored_scope() if coverage_mode == "partial" else None
                execution_id = lab.start_execution(scope)
                transformed = lab.invoke(execution_id, "data-transformer", {
                    "asset_ids": ["asset:confidential:case-7"], "title": "No-egress report"})
                lab.invoke(execution_id, "workspace-storage", {
                    "file_id": transformed["output"]["file_id"]})
                if coverage_mode == "partial":
                    lab.note_coverage_gap(execution_id, "UNRELATED_INTERFACE")
                report = lab.finish_execution(execution_id)
                result = analyze(lab, report, [active_rule])
                self.assertIn(report.coverage.status, {CoverageStatus.PARTIAL, CoverageStatus.UNKNOWN})
                self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)
                self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION
                                     for item in result.findings))
                self.assertNotEqual(result.status,
                                    AnalysisStatus.NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE)

    def test_policy_coverage_evidence_requirement_blocks_decision_under_partial_scope(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        confidential_external_workflow(lab, execution_id)
        lab.note_coverage_gap(execution_id, "UNRELATED_POLICY_INTERFACE")
        report = lab.finish_execution(execution_id)
        coverage_rule = policy().model_copy(update={
            "evidence_requirements": ["event_path", "observed_event", "coverage"]})
        result = analyze(lab, report, [coverage_rule])

        self.assertEqual(report.coverage.status, CoverageStatus.PARTIAL)
        self.assertEqual(result.status, AnalysisStatus.POTENTIAL_RISK)
        evaluation = next(item for item in result.policy_evaluations
                          if item.policy_rule_id == coverage_rule.rule_id)
        self.assertEqual(evaluation.decision, PolicyDecision.INCONCLUSIVE)
        self.assertTrue(set(report.coverage.evidence_ids).issubset(evaluation.evidence_ids))
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION
                             for item in result.findings))

    def test_e_positive_prohibited_event_can_confirm_under_partial_wider_coverage(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        confidential_external_workflow(lab, execution_id)
        lab.note_coverage_gap(execution_id, "UNRELATED_MONITOR")
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report, [policy()])

        self.assertEqual(report.coverage.status, CoverageStatus.PARTIAL)
        self.assertEqual(result.status, AnalysisStatus.CONFIRMED_VIOLATION)
        finding = next(item for item in result.findings
                       if item.assessment == Assessment.CONFIRMED_VIOLATION)
        self.assertEqual(finding.coverage_status, CoverageStatus.PARTIAL)
        self.assertIn("r2_monitoring_coverage_not_complete", result.incomplete_reasons)

    def test_f_external_destination_is_allowed_only_by_explicit_valid_rule(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "public-share.txt"})
        lab.invoke(execution_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        authorization = policy(
            rule_id="POL-EXTERNAL-AUTHORIZED", outcome="ALLOW",
            conditions={"authorized_destinations": [EXTERNAL_DESTINATION],
                        "maximum_classification": "PUBLIC"})
        result = analyze(lab, report, [authorization])

        self.assertEqual(result.status, AnalysisStatus.NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE)
        self.assertTrue(any(item.decision == PolicyDecision.ALLOW and
                            item.applicability == PolicyApplicability.APPLICABLE
                            for item in result.policy_evaluations))
        self.assertFalse(any(item.assessment in {Assessment.CONFIRMED_VIOLATION,
                                                 Assessment.POTENTIAL_RISK}
                             for item in result.findings))

    def test_g_inactive_or_out_of_scope_policy_is_recorded_but_not_confirmed(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        confidential_external_workflow(lab, execution_id)
        report = lab.finish_execution(execution_id)
        inactive = policy("POL-INACTIVE", active=False)
        out_of_scope = policy("POL-OTHER-DEST", scope={"destination_ids": [INTERNAL_DESTINATION]})
        result = analyze(lab, report, [inactive, out_of_scope])

        applicability = {(item.policy_rule_id, item.applicability) for item in result.policy_evaluations}
        self.assertIn((inactive.rule_id, PolicyApplicability.INACTIVE), applicability)
        self.assertIn((out_of_scope.rule_id, PolicyApplicability.OUT_OF_SCOPE), applicability)
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION and
                             item.policy_rule_id in {inactive.rule_id, out_of_scope.rule_id}
                             for item in result.findings))

    def test_policy_restricts_unauthorized_asset_access(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        lab.invoke(execution_id, "document-reader", {"asset_id": "asset:confidential:case-7"})
        report = lab.finish_execution(execution_id)
        access_rule = policy(
            rule_id="POL-ASSET-ALLOWLIST", kind=PolicyKind.RESTRICT_ASSET_ACCESS,
            scope={"tool_ids": ["document-reader"]},
            conditions={"allowed_resources": ["asset:public:handbook"]})
        result = analyze(lab, report, [access_rule])

        self.assertEqual(result.status, AnalysisStatus.CONFIRMED_VIOLATION)
        finding = next(item for item in result.findings
                       if item.assessment == Assessment.CONFIRMED_VIOLATION)
        self.assertEqual(finding.policy_rule_id, access_rule.rule_id)

    def test_policy_restricts_write_to_prohibited_resource(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "write-policy.txt"})
        lab.invoke(execution_id, "workspace-storage", {"file_id": created["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        write_event = next(event for event in report.events if event.effect_type == EffectType.WRITES)
        write_rule = policy(
            rule_id="POL-WRITE-DENY", kind=PolicyKind.RESTRICT_WRITE_DESTINATION,
            scope={"tool_ids": ["workspace-storage"]},
            conditions={"prohibited_resources": [write_event.destination_resource]})
        result = analyze(lab, report, [write_rule])

        self.assertEqual(result.status, AnalysisStatus.CONFIRMED_VIOLATION)
        self.assertTrue(any(item.policy_rule_id == write_rule.rule_id and
                            item.assessment == Assessment.CONFIRMED_VIOLATION
                            for item in result.findings))

    def test_policy_explicitly_prohibits_destination_for_public_data(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "public-prohibited.txt"})
        lab.invoke(execution_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        destination_rule = policy(
            rule_id="POL-EXPLICIT-DEST-DENY", kind=PolicyKind.PROHIBIT_DESTINATION,
            conditions={"prohibited_destinations": [EXTERNAL_DESTINATION]})
        result = analyze(lab, report, [destination_rule])

        self.assertEqual(result.status, AnalysisStatus.CONFIRMED_VIOLATION)
        self.assertEqual(next(item for item in result.findings
                              if item.assessment == Assessment.CONFIRMED_VIOLATION).severity,
                         Severity.MEDIUM)

    def test_approval_absence_is_not_confirmed_without_approval_coverage(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "approval-policy.txt"})
        lab.invoke(execution_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        approval_rule = policy(
            rule_id="POL-APPROVAL", kind=PolicyKind.APPROVAL_REQUIRED,
            scope={"tool_ids": ["file-sharing"]},
            conditions={"effect_types": [EffectType.TRANSMITS.value]},
            outcome="REQUIRE_APPROVAL")
        approval_rule = approval_rule.model_copy(update={
            "evidence_requirements": ["event_path", "observed_event", "approval_event"]})
        result = analyze(lab, report, [approval_rule])

        self.assertEqual(result.status, AnalysisStatus.POTENTIAL_RISK)
        self.assertTrue(any(item.policy_rule_id == approval_rule.rule_id and
                            item.decision == PolicyDecision.INCONCLUSIVE
                            for item in result.policy_evaluations))
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION
                             for item in result.findings))

    def test_h_missing_transform_lineage_creates_no_asset_to_output_path(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        original_record = lab.recorder.record

        def drop_transform_lineage(**kwargs):
            if kwargs.get("effect_type") == EffectType.TRANSFORMS:
                kwargs["source_resource"] = None
                kwargs["metadata"] = {key: value for key, value in kwargs.get("metadata", {}).items()
                                       if key != "source_asset_ids"}
            return original_record(**kwargs)

        with patch.object(lab.recorder, "record", side_effect=drop_transform_lineage):
            lab.invoke(execution_id, "data-transformer", {
                "asset_ids": ["asset:confidential:case-7"], "title": "Lineage gap"})
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report)

        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)
        self.assertTrue(any(item.category == MismatchCategory.INCOMPLETE_COMPARISON
                            and item.observed_effect == EffectType.TRANSFORMS
                            for item in result.mismatches))
        source_node = f"{execution_id}::resource::asset:confidential:case-7"
        transform_events = {event.event_id for event in report.events
                            if event.effect_type == EffectType.TRANSFORMS}
        self.assertTrue(transform_events)
        self.assertFalse(any(path.node_ids[0] == source_node and
                             set(path.event_ids).intersection(transform_events)
                             for path in result.paths))
        self.assertIn("transformation_lineage_missing", result.incomplete_reasons)


class ComparisonAndIntegrityTests(unittest.TestCase):
    def _manifest_with_transmit_expectation(self, lab, *, optional=False):
        manifests = lab.registry.list_manifests()
        updated = []
        for item in manifests:
            if item.tool_id == "workspace-storage":
                updated.append(item.model_copy(update={
                    "declared_effects": [EffectType.READS, EffectType.WRITES, EffectType.TRANSMITS],
                    "optional_effects": [EffectType.TRANSMITS] if optional else [],
                    "declared_capabilities": [*item.declared_capabilities, "share_file"],
                    "permission_scope": [*item.permission_scope, "destination.transmit"],
                    "allowed_destinations": [EXTERNAL_DESTINATION],
                }))
            else:
                updated.append(item)
        return updated

    def test_missing_expected_effect_confirmed_only_for_success_and_complete_relevant_scope(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "expected-effect.txt"})
        lab.invoke(execution_id, "workspace-storage", {"file_id": created["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report, manifests=self._manifest_with_transmit_expectation(lab))
        self.assertTrue(any(item.category == MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED
                            and item.expected_effect == EffectType.TRANSMITS
                            and item.assessment == Assessment.EFFECT_MISMATCH
                            for item in result.mismatches))

    def test_partial_coverage_makes_missing_expected_effect_inconclusive(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "expected-effect-partial.txt"})
        lab.invoke(execution_id, "workspace-storage", {"file_id": created["output"]["file_id"]})
        lab.note_coverage_gap(execution_id, "SEARCH_BOUNDARY")
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report, manifests=self._manifest_with_transmit_expectation(lab))
        self.assertFalse(any(item.category == MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED
                             and item.expected_effect == EffectType.TRANSMITS for item in result.mismatches))
        self.assertTrue(any(item.category == MismatchCategory.INCOMPLETE_COMPARISON
                            and item.expected_effect == EffectType.TRANSMITS for item in result.mismatches))
        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)

    def test_optional_effect_is_not_required_and_failed_invocation_is_not_omission(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "optional-effect.txt"})
        lab.invoke(execution_id, "workspace-storage", {"file_id": created["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        optional_result = analyze(lab, report, manifests=self._manifest_with_transmit_expectation(lab, optional=True))
        self.assertFalse(any(item.expected_effect == EffectType.TRANSMITS and item.category in {
            MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED, MismatchCategory.INCOMPLETE_COMPARISON}
            for item in optional_result.mismatches))

        failed_lab = LabRunner()
        failed_id = failed_lab.start_execution(default_monitored_scope())
        failed_lab.invoke(failed_id, "workspace-storage", {"file_id": "file:missing"})
        failed_report = failed_lab.finish_execution(failed_id)
        failed_result = analyze(failed_lab, failed_report,
                                manifests=self._manifest_with_transmit_expectation(failed_lab))
        self.assertFalse(any(item.category == MismatchCategory.EXPECTED_EFFECT_NOT_OBSERVED
                             for item in failed_result.mismatches))
        self.assertTrue(any(item.category == MismatchCategory.INCOMPLETE_COMPARISON
                            for item in failed_result.mismatches))

    def test_duplicate_manifest_identity_is_incomplete_not_order_dependent(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
        report = lab.finish_execution(execution_id)
        manifests = lab.registry.list_manifests()
        manifests.append(next(item for item in manifests if item.tool_id == "document-reader")
                         .model_copy(update={"description": "conflicting duplicate identity"}))
        result = analyze(lab, report, manifests=manifests)

        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)
        self.assertTrue(any(item.category == MismatchCategory.INCOMPLETE_COMPARISON
                            and item.tool_id == "document-reader" for item in result.mismatches))

    def test_duplicate_policy_id_and_version_are_not_applied(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "duplicate-policy.txt"})
        lab.invoke(execution_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        first = policy("POL-DUPLICATE")
        conflicting = first.model_copy(update={"outcome": "ALLOW"})
        result = analyze(lab, report, [first, conflicting])

        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)
        self.assertIn("duplicate_policy_identity", result.incomplete_reasons)
        self.assertTrue(all(item.applicability == PolicyApplicability.UNSUPPORTED_RULE
                            for item in result.policy_evaluations))
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION
                             for item in result.findings))

    def test_confirmed_policy_requires_exact_graph_event_and_resolvable_path_evidence(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        confidential_external_workflow(lab, execution_id)
        report = lab.finish_execution(execution_id)
        active_rule = policy()
        result = analyze(lab, report, [active_rule])
        valid_evaluation = next(item for item in result.policy_evaluations
                                if item.decision == PolicyDecision.DENY)
        unrelated_event = report.events[0]

        for corrupted in (
                valid_evaluation.model_copy(update={"event_ids": [unrelated_event.event_id]}),
                valid_evaluation.model_copy(update={"evidence_ids": ["evidence:not-present"]})):
            findings = FindingGenerator().generate(
                execution_id=execution_id, coverage=report.coverage, mismatches=(),
                policy_evaluations=[corrupted], policies=[active_rule], events=report.events,
                paths=result.paths, evidence_store=lab.evidence_store)
            self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION for item in findings))

    def test_r2_duplicate_invocation_identity_excludes_its_events_from_graph(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
        report = lab.finish_execution(execution_id)
        duplicate = replace(report.invocations[0], tool_id="file-creator")
        ambiguous_report = replace(report, invocations=(*report.invocations, duplicate))
        result = analyze(lab, ambiguous_report)

        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)
        self.assertIn("event_invocation_identity_ambiguous", result.incomplete_reasons)
        self.assertFalse(any(edge.event_ids and edge.event_ids[0] == report.events[0].event_id
                             for edge in result.graph_edges))

    def test_empty_explicit_destination_prohibition_is_unsupported(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "empty-denylist.txt"})
        lab.invoke(execution_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        empty_rule = policy(
            rule_id="POL-EMPTY-DENYLIST", kind=PolicyKind.PROHIBIT_DESTINATION,
            conditions={"prohibited_destinations": []})
        result = analyze(lab, report, [empty_rule])

        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)
        self.assertTrue(any(item.policy_rule_id == empty_rule.rule_id and
                            item.applicability == PolicyApplicability.UNSUPPORTED_RULE
                            for item in result.policy_evaluations))

    def test_unsupported_policy_outcomes_and_evidence_requirements_fail_closed(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "unsupported-policy.txt"})
        lab.invoke(execution_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        bad_outcome = policy(rule_id="POL-BAD-OUTCOME").model_copy(update={"outcome": "BLOCK"})
        bad_requirement = policy(rule_id="POL-BAD-EVIDENCE").model_copy(update={
            "evidence_requirements": ["event_path", "unrecognized-proof"]})
        approval_allows = policy(
            rule_id="POL-APPROVAL-ALLOW", kind=PolicyKind.APPROVAL_REQUIRED,
            scope={"tool_ids": ["file-sharing"]},
            conditions={"effect_types": [EffectType.TRANSMITS.value]}, outcome="ALLOW")
        result = analyze(lab, report, [bad_outcome, bad_requirement, approval_allows])

        unsupported = {item.policy_rule_id for item in result.policy_evaluations
                       if item.applicability == PolicyApplicability.UNSUPPORTED_RULE}
        self.assertEqual(unsupported, {bad_outcome.rule_id, bad_requirement.rule_id, approval_allows.rule_id})
        self.assertFalse(any(item.assessment == Assessment.CONFIRMED_VIOLATION for item in result.findings))

    def test_all_six_legitimate_r2_tools_match_their_manifest_operations(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        with patch.object(socket, "socket", side_effect=AssertionError("network socket forbidden")):
            lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
            lab.invoke(execution_id, "database-search", {
                "dataset_id": "dataset:synthetic-cases", "query": "active"})
            transformed = lab.invoke(execution_id, "data-transformer", {
                "asset_ids": ["asset:internal:ops", "asset:confidential:case-7"],
                "title": "Synthetic combined report"})
            created = lab.invoke(execution_id, "file-creator", {
                "asset_id": "asset:restricted:fixture", "filename": "restricted-copy.txt"})
            stored = lab.invoke(execution_id, "workspace-storage", {
                "file_id": transformed["output"]["file_id"]})
            lab.invoke(execution_id, "file-sharing", {
                "file_id": stored["output"]["stored_file_id"],
                "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report)

        self.assertFalse(any(item.category == MismatchCategory.UNEXPECTED_OPERATION
                             for item in result.mismatches))
        self.assertFalse(any(item.category == MismatchCategory.UNEXPECTED_RESOURCE_OR_DESTINATION
                             for item in result.mismatches))

    def test_cross_execution_records_never_form_one_graph_path(self):
        lab = LabRunner()
        first_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(first_id, "file-creator", {
            "asset_id": "asset:confidential:case-7", "filename": "prior-run.txt"})
        lab.finish_execution(first_id)
        second_id = lab.start_execution(default_monitored_scope())
        lab.invoke(second_id, "file-sharing", {
            "file_id": created["output"]["file_id"], "destination_id": EXTERNAL_DESTINATION})
        second_report = lab.finish_execution(second_id)
        result = analyze(lab, second_report)

        self.assertTrue(all(node.execution_id == second_id for node in result.graph_nodes))
        self.assertTrue(all(edge.execution_id == second_id for edge in result.graph_edges))
        self.assertTrue(all(path.execution_id == second_id for path in result.paths))
        self.assertFalse(any(node.resource_id == "asset:confidential:case-7" for node in result.graph_nodes))
        self.assertTrue(any(path.destination_id == EXTERNAL_DESTINATION for path in result.paths))

    def test_cycle_safe_traversal_terminates_without_repeating_nodes(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
        report = lab.finish_execution(execution_id)
        result = analyze(lab, report)
        event = report.events[0]
        nodes = {node.node_id: node for node in result.graph_nodes}
        asset_node = next(node for node in nodes.values() if node.resource_id == "asset:public:handbook")
        tool_node = next(node for node in nodes.values() if node.node_type == "TOOL")
        real_edge = result.graph_edges[0]
        cycle_edge = GraphEdge(
            edge_id="edge:test-cycle", source_node_id=tool_node.node_id,
            target_node_id=asset_node.node_id, edge_type=GraphEdgeType.USES,
            execution_id=execution_id, event_ids=[event.event_id],
            classification=event.classification, evidence_ids=[event.evidence[0].evidence_id],
            invocation_ids=[event.invocation_id],
        )
        cyclic_paths, truncation_reasons = CapabilityGraphBuilder()._enumerate_paths(
            execution_id, tuple(nodes.values()), tuple(result.graph_edges) + (cycle_edge,))
        self.assertTrue(cyclic_paths)
        self.assertFalse(truncation_reasons)
        self.assertTrue(all(len(path.node_ids) == len(set(path.node_ids)) for path in cyclic_paths))
        self.assertTrue(real_edge.event_ids)


class GraphTruncationTests(unittest.TestCase):
    @staticmethod
    def _safe_report():
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        transformed = lab.invoke(execution_id, "data-transformer", {
            "asset_ids": ["asset:public:handbook"], "title": "Internal report"})
        lab.invoke(execution_id, "workspace-storage", {
            "file_id": transformed["output"]["file_id"]})
        return lab, lab.finish_execution(execution_id)

    def test_effect_enum_excludes_graph_only_uses_relation(self):
        self.assertNotIn("USES", EffectType.__members__)
        self.assertEqual(GraphEdgeType("USES"), GraphEdgeType.USES)
        with self.assertRaises(ValueError):
            EffectType("USES")

    def test_depth_limit_marks_result_inconclusive(self):
        lab, report = self._safe_report()
        result = AnalysisService(graph_builder=CapabilityGraphBuilder(max_depth=1)).analyze(
            report, lab.registry.list_manifests(), (), lab.evidence_store)
        self.assertTrue(result.graph_truncated)
        self.assertIn("graph_depth_limit_reached", result.graph_truncation_reasons)
        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)

    def test_path_limit_marks_result_inconclusive(self):
        lab, report = self._safe_report()
        result = AnalysisService(graph_builder=CapabilityGraphBuilder(max_paths=1)).analyze(
            report, lab.registry.list_manifests(), (), lab.evidence_store)
        self.assertTrue(result.graph_truncated)
        self.assertIn("graph_path_limit_reached", result.graph_truncation_reasons)
        self.assertEqual(result.status, AnalysisStatus.INCONCLUSIVE)

    def test_truncated_result_cannot_claim_unqualified_no_violation(self):
        lab, report = self._safe_report()
        result = AnalysisService(graph_builder=CapabilityGraphBuilder(max_paths=1)).analyze(
            report, lab.registry.list_manifests(), (), lab.evidence_store)
        payload = result.model_dump()
        payload.update(
            status=AnalysisStatus.NO_VIOLATION_OBSERVED_WITHIN_COMPLETE_SCOPE,
            incomplete_reasons=["graph_path_limit_reached"],
        )
        with self.assertRaisesRegex(ValueError, "no-violation conclusion"):
            AnalysisResult.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
