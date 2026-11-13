import socket
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.core.schemas.contracts import Assessment, CoverageStatus, EffectType
from app.sandbox.resources import (
    EXTERNAL_DESTINATION, INSTRUMENTED_INTERFACES, INTERNAL_DESTINATION,
)
from app.sandbox.runner import LabRunner, default_monitored_scope
from app.tools.lab_tools import DocumentReader
from app.tools.registry import DuplicateToolError, UnknownToolError


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.lab = LabRunner()

    def test_six_approved_tools_register_with_implementation_references(self):
        manifests = self.lab.registry.list_manifests()
        self.assertEqual(len(manifests), 6)
        self.assertEqual({item.tool_id for item in manifests}, {
            "document-reader", "database-search", "data-transformer",
            "file-creator", "workspace-storage", "file-sharing",
        })
        for item in manifests:
            self.assertTrue(self.lab.registry.get_implementation_reference(item.tool_id))

    def test_duplicate_registration_is_rejected(self):
        with self.assertRaises(DuplicateToolError):
            self.lab.registry.register(DocumentReader())

    def test_unknown_tool_lookup_fails_safely(self):
        with self.assertRaises(UnknownToolError):
            self.lab.registry.get_manifest("unregistered-tool")

    def test_registry_rejects_unapproved_implementation_type(self):
        class LookalikeReader(DocumentReader):
            pass
        with self.assertRaises(ValueError):
            self.lab.registry.register(LookalikeReader())

    def test_registry_rejects_invalid_manifest(self):
        tool = DocumentReader()
        tool.manifest = tool.manifest.model_copy(update={"tool_id": "invalid id"})
        with self.assertRaises(ValidationError):
            self.lab.registry.register(tool)

    def test_registry_rejects_unsupported_manifest_schema(self):
        tool = DocumentReader()
        tool.manifest = tool.manifest.model_copy(update={"input_schema": {"type": "arbitrary"}})
        with self.assertRaises(ValueError):
            self.lab.registry.register(tool)

    def test_invalid_input_is_rejected_before_resource_operations(self):
        execution_id = self.lab.start_execution(default_monitored_scope())
        result = self.lab.invoke(execution_id, "document-reader", {})
        report = self.lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], "INVALID_INPUT")
        self.assertEqual(report.events, ())
        self.assertEqual(report.coverage.status, CoverageStatus.COMPLETE)
        self.assertTrue(self.lab.evidence_store.resolve(
            report.invocations[0].failure_evidence_id).sha256)


class ControlledExecutionTests(unittest.TestCase):
    def test_all_six_tools_perform_real_local_operations_and_emit_provenanced_events(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        with patch.object(socket, "socket", side_effect=AssertionError("network socket forbidden")):
            read = lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
            search = lab.invoke(execution_id, "database-search", {
                "dataset_id": "dataset:synthetic-cases", "query": "active"})
            transform = lab.invoke(execution_id, "data-transformer", {
                "asset_ids": ["asset:internal:ops", "asset:confidential:case-7"],
                "title": "Synthetic combined report"})
            create = lab.invoke(execution_id, "file-creator", {
                "asset_id": "asset:restricted:fixture", "filename": "restricted-copy.txt"})
            store = lab.invoke(execution_id, "workspace-storage", {
                "file_id": transform["output"]["file_id"]})
            share = lab.invoke(execution_id, "file-sharing", {
                "file_id": store["output"]["stored_file_id"],
                "destination_id": EXTERNAL_DESTINATION})
        report = lab.finish_execution(execution_id)

        for result in (read, search, transform, create, store, share):
            self.assertEqual(result["status"], "SUCCEEDED", result)
        self.assertEqual(len(search["output"]["records"]), 2, "query must filter actual synthetic rows")
        self.assertEqual(transform["output"]["classification"], "CONFIDENTIAL")
        self.assertEqual(transform["output"]["source_asset_ids"],
                         ["asset:internal:ops", "asset:confidential:case-7"])
        self.assertEqual(create["output"]["classification"], "RESTRICTED")
        self.assertEqual(share["output"]["destination_id"], EXTERNAL_DESTINATION)
        self.assertTrue(lab.destinations.is_external(EXTERNAL_DESTINATION))
        self.assertEqual(len(lab.destinations.deliveries(EXTERNAL_DESTINATION)), 1)
        self.assertEqual(report.coverage.status, CoverageStatus.COMPLETE)
        self.assertGreaterEqual(len(report.events), 11)
        self.assertEqual([event.sequence for event in report.events], list(range(1, len(report.events) + 1)))
        self.assertTrue({EffectType.READS, EffectType.SEARCHES, EffectType.TRANSFORMS,
                         EffectType.CREATES, EffectType.WRITES, EffectType.TRANSMITS}
                        .issubset({event.effect_type for event in report.events}))
        invocation_ids = {item.invocation_id for item in report.invocations}
        for event in report.events:
            self.assertEqual(event.execution_id, execution_id)
            self.assertIn(event.invocation_id, invocation_ids)
            self.assertTrue(event.tool_id)
            self.assertIsNotNone(event.occurred_at.tzinfo)
            self.assertEqual(event.outcome, "SUCCESS")
            self.assertEqual(len(event.evidence), 1)
            self.assertTrue(lab.evidence_store.verify(event.evidence[0]))
            record = lab.evidence_store.resolve(event.evidence[0].evidence_id)
            self.assertEqual(record.payload()["event_id"], event.event_id)
            self.assertNotIn("content", event.metadata)
            self.assertNotIn("query", event.metadata)
        self.assertTrue(all(lab.evidence_store.resolve(item).evidence_id == item
                            for item in report.coverage.evidence_ids))

    def test_search_uses_query_and_limit_instead_of_hardcoded_output(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        active = lab.invoke(execution_id, "database-search", {
            "dataset_id": "dataset:synthetic-cases", "query": "active", "limit": 1})
        closed = lab.invoke(execution_id, "database-search", {
            "dataset_id": "dataset:synthetic-cases", "query": "closed"})
        lab.finish_execution(execution_id)
        self.assertEqual([row["record_id"] for row in active["output"]["records"]], ["case:001"])
        self.assertEqual([row["record_id"] for row in closed["output"]["records"]], ["case:002"])

    def test_failed_controlled_read_has_failed_event_and_resolvable_evidence(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        result = lab.invoke(execution_id, "document-reader", {
            "asset_id": "asset:public:handbook", "fields": ["not-a-field"]})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], "FIELD_NOT_FOUND")
        failed = [event for event in report.events if event.outcome == "FAILED"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].effect_type, EffectType.READS)
        self.assertTrue(lab.evidence_store.verify(failed[0].evidence[0]))
        self.assertEqual(report.coverage.status, CoverageStatus.COMPLETE)

    def test_untrusted_resource_identifier_is_redacted_from_event_evidence(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        marker = "demo-secret-resource"
        result = lab.invoke(execution_id, "document-reader", {"asset_id": marker})
        report = lab.finish_execution(execution_id)
        event = report.events[0]
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(event.source_resource, "resource:unresolved")
        self.assertEqual(event.metadata["asset_id"], "resource:unresolved")
        event_record = lab.evidence_store.resolve(event.evidence[0].evidence_id)
        failure_record = lab.evidence_store.resolve(report.invocations[0].failure_evidence_id)
        self.assertNotIn(marker, event_record.canonical_payload)
        self.assertNotIn(marker, failure_record.canonical_payload)

    def test_unknown_tool_identifier_is_redacted_from_failure_evidence(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        marker = "demo-secret-tool-id"
        result = lab.invoke(execution_id, marker, {})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        evidence = lab.evidence_store.resolve(report.invocations[0].failure_evidence_id)
        self.assertNotIn(marker, evidence.canonical_payload)
        self.assertEqual(evidence.payload()["tool_id"], "tool:unresolved")

    def test_invalid_file_write_records_attempt_failure_evidence(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        result = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "../escape.txt"})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        failed_creates = [event for event in report.events
                          if event.effect_type == EffectType.CREATES and event.outcome == "FAILED"]
        self.assertEqual(len(failed_creates), 1)
        self.assertEqual(failed_creates[0].metadata["reason_code"], "INVALID_FILE_NAME")
        self.assertTrue(lab.evidence_store.verify(failed_creates[0].evidence[0]))
        self.assertNotIn("../escape.txt", lab.evidence_store.resolve(
            failed_creates[0].evidence[0].evidence_id).canonical_payload)

    def test_recorder_failure_fails_closed_and_rolls_back_staged_write(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "to-store.txt"})
        self.assertEqual(created["status"], "SUCCEEDED")
        before = len(lab.workspace._files)
        lab.recorder.fail_next_for(EffectType.WRITES)
        failed = lab.invoke(execution_id, "workspace-storage", {
            "file_id": created["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["error_code"], "INJECTED_RECORDER_FAILURE")
        self.assertEqual(len(lab.workspace._files), before, "unrecorded write must be rolled back")
        self.assertFalse(any(event.effect_type == EffectType.WRITES for event in report.events))
        self.assertEqual(report.coverage.status, CoverageStatus.FAILED)
        self.assertTrue(report.coverage.gaps)

    def test_evidence_store_failure_is_not_reported_as_success(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        created = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:public:handbook", "filename": "evidence-failure.txt"})
        before = len(lab.workspace._files)
        original_create = lab.evidence_store.create

        def fail_write_event(kind, facts):
            if kind == "observed_effect" and facts.get("effect_type") == EffectType.WRITES.value:
                raise OSError("synthetic evidence-store failure")
            return original_create(kind, facts)

        with patch.object(lab.evidence_store, "create", side_effect=fail_write_event):
            result = lab.invoke(execution_id, "workspace-storage", {
                "file_id": created["output"]["file_id"]})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], "RECORDER_RECORD_FAILED")
        self.assertEqual(len(lab.workspace._files), before)
        self.assertFalse(any(event.effect_type == EffectType.WRITES for event in report.events))
        self.assertEqual(report.coverage.status, CoverageStatus.FAILED)

    def test_self_check_failure_blocks_tool_operations(self):
        lab = LabRunner()
        lab.recorder.active = False
        execution_id = lab.start_execution(default_monitored_scope())
        result = lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(report.events), 0)
        self.assertEqual(report.coverage.status, CoverageStatus.FAILED)


class CoverageAndLineageTests(unittest.TestCase):
    def test_complete_coverage_has_scope_selfcheck_and_resolving_evidence(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        lab.invoke(execution_id, "document-reader", {"asset_id": "asset:public:handbook"})
        report = lab.finish_execution(execution_id)
        self.assertEqual(report.coverage.status, CoverageStatus.COMPLETE)
        self.assertEqual(set(report.coverage.monitored_scope), INSTRUMENTED_INTERFACES)
        for evidence_id in report.coverage.evidence_ids:
            self.assertIsNotNone(lab.evidence_store.resolve(evidence_id))

    def test_detected_scope_gap_is_partial_not_safe(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        lab.note_coverage_gap(execution_id, "ADAPTER_BYPASS_DETECTED")
        report = lab.finish_execution(execution_id)
        self.assertEqual(report.coverage.status, CoverageStatus.PARTIAL)
        self.assertEqual(Assessment.INCONCLUSIVE,
                         __import__("app.core.schemas.contracts", fromlist=["assess_absence_of_violation"])
                         .assess_absence_of_violation(report.coverage.status, False))

    def test_missing_scope_is_unknown(self):
        lab = LabRunner()
        execution_id = lab.start_execution()
        report = lab.finish_execution(execution_id)
        self.assertEqual(report.coverage.status, CoverageStatus.UNKNOWN)
        self.assertFalse(report.coverage.monitored_scope)

    def test_multi_input_transform_preserves_lineage_and_highest_sensitivity(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        result = lab.invoke(execution_id, "data-transformer", {
            "asset_ids": ["asset:public:handbook", "asset:restricted:fixture"],
            "title": "Two-source report"})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["output"]["classification"], "RESTRICTED")
        self.assertEqual(result["output"]["source_asset_ids"],
                         ["asset:public:handbook", "asset:restricted:fixture"])
        transform_event = next(event for event in report.events if event.effect_type == EffectType.TRANSFORMS)
        self.assertEqual(transform_event.classification.value, "RESTRICTED")
        self.assertEqual(transform_event.metadata["source_asset_ids"], result["output"]["source_asset_ids"])


class AdversarialFixtureTests(unittest.TestCase):
    def _create_file(self, lab, execution_id):
        result = lab.invoke(execution_id, "file-creator", {
            "asset_id": "asset:confidential:case-7", "filename": "report-source.txt"})
        self.assertEqual(result["status"], "SUCCEEDED")
        return result["output"]["file_id"]

    def test_normal_workspace_storage_only_writes_internally(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        file_id = self._create_file(lab, execution_id)
        result = lab.invoke(execution_id, "workspace-storage", {"file_id": file_id})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertNotIn("adversarial_delivery_id", result["output"])
        storage_events = [event for event in report.events if event.tool_id == "workspace-storage"]
        self.assertEqual([event.effect_type for event in storage_events], [EffectType.READS, EffectType.WRITES])
        self.assertEqual(lab.destinations.deliveries(EXTERNAL_DESTINATION), [])
        manifest = lab.registry.get_manifest("workspace-storage")
        self.assertNotIn(EffectType.TRANSMITS, manifest.declared_effects)

    def test_adversarial_fixture_records_internal_write_and_simulated_external_copy(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope(), adversarial_storage_external_copy=True)
        file_id = self._create_file(lab, execution_id)
        result = lab.invoke(execution_id, "workspace-storage", {"file_id": file_id})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "SUCCEEDED")
        storage_events = [event for event in report.events if event.tool_id == "workspace-storage"]
        self.assertEqual([event.effect_type for event in storage_events],
                         [EffectType.READS, EffectType.WRITES, EffectType.TRANSMITS])
        self.assertEqual(storage_events[-1].destination_resource, EXTERNAL_DESTINATION)
        self.assertTrue(storage_events[-1].metadata["adversarial_fixture"])
        deliveries = lab.destinations.deliveries(EXTERNAL_DESTINATION)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].classification.value, "CONFIDENTIAL")
        self.assertTrue(all(lab.evidence_store.verify(event.evidence[0]) for event in storage_events))
        self.assertEqual(report.coverage.status, CoverageStatus.COMPLETE)

    def test_internal_and_external_destinations_are_local_only(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope())
        file_id = self._create_file(lab, execution_id)
        with patch.object(socket, "socket", side_effect=AssertionError("network socket forbidden")):
            internal = lab.invoke(execution_id, "file-sharing", {
                "file_id": file_id, "destination_id": INTERNAL_DESTINATION})
            external = lab.invoke(execution_id, "file-sharing", {
                "file_id": file_id, "destination_id": EXTERNAL_DESTINATION})
        lab.finish_execution(execution_id)
        self.assertEqual(internal["status"], "SUCCEEDED")
        self.assertEqual(external["status"], "SUCCEEDED")
        self.assertEqual(len(lab.destinations.deliveries(INTERNAL_DESTINATION)), 1)
        self.assertEqual(len(lab.destinations.deliveries(EXTERNAL_DESTINATION)), 1)

    def test_adversarial_override_cannot_be_used_by_other_tools(self):
        lab = LabRunner()
        execution_id = lab.start_execution(default_monitored_scope(), adversarial_storage_external_copy=True)
        file_id = self._create_file(lab, execution_id)
        # The ordinary sharing tool has no manifest permission to bypass its destination allowlist.
        result = lab.invoke(execution_id, "file-sharing", {
            "file_id": file_id, "destination_id": "destination:unknown"})
        report = lab.finish_execution(execution_id)
        self.assertEqual(result["status"], "FAILED")
        failed_event = next(event for event in report.events if event.outcome == "FAILED")
        self.assertEqual(failed_event.destination_resource, "destination:unresolved")
        self.assertNotIn("destination:unknown", lab.evidence_store.resolve(
            failed_event.evidence[0].evidence_id).canonical_payload)
        self.assertEqual(lab.destinations.deliveries("destination:unknown"), [])


if __name__ == "__main__":
    unittest.main()
