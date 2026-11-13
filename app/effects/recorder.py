"""Shared recorder used exclusively by controlled resource adapters."""
from __future__ import annotations

import threading
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.schemas.contracts import Classification, EffectType, ObservedEffect
from app.effects.evidence_store import EvidenceStore


class RecorderUnavailable(RuntimeError):
    """Raised when an effect cannot be recorded reliably; callers must fail closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


SAFE_METADATA_KEYS = {
    "asset_id", "dataset_id", "result_count", "record_count", "input_count", "field_count",
    "source_asset_ids", "output_resource_id", "file_id", "workspace_id",
    "destination_id", "delivery_id", "adversarial_fixture", "reason_code", "query_length",
    "fixture_id", "transform_id", "classification_basis",
}


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Copy only allowlisted identifiers, booleans, and counts; never arbitrary content."""
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in SAFE_METADATA_KEYS:
            continue
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
        elif (isinstance(value, str) and len(value) <= 128
              and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/-]{0,127}", value)):
            safe[key] = value
        elif isinstance(value, (list, tuple)) and len(value) <= 32 and all(
                isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._/-]{0,127}", item)
                for item in value):
            safe[key] = list(value)
    return safe


class EffectRecorder:
    VERSION = "r2-recorder/1.0"

    def __init__(self, evidence_store: EvidenceStore) -> None:
        self._evidence_store = evidence_store
        self._events: dict[str, list[ObservedEffect]] = {}
        self._sequences: dict[str, int] = {}
        self._lock = threading.RLock()
        self.active = True
        self._fail_effect_once: EffectType | None = None

    def self_check(self, execution_id: str, monitored_scope: list[str]):
        if not self.active:
            raise RecorderUnavailable("RECORDER_INACTIVE")
        return self._evidence_store.create("recorder_self_check", {
            "execution_id": execution_id,
            "recorder_version": self.VERSION,
            "monitored_scope": list(monitored_scope),
            "active": True,
        })

    def fail_next_for(self, effect_type: EffectType) -> None:
        """Deterministic test hook: fail the next matching record, never a production bypass."""
        self._fail_effect_once = effect_type

    def record(self, *, execution_id: str, invocation_id: str, tool_id: str,
               effect_type: EffectType, operation: str, source_resource: str | None,
               destination_resource: str | None, classification: Classification,
               outcome: str, metadata: dict[str, Any] | None = None) -> ObservedEffect:
        with self._lock:
            if not self.active:
                raise RecorderUnavailable("RECORDER_INACTIVE")
            if self._fail_effect_once == effect_type:
                self._fail_effect_once = None
                raise RecorderUnavailable("INJECTED_RECORDER_FAILURE")
            try:
                safe_meta = _safe_metadata(metadata or {})
                sequence = self._sequences.get(execution_id, 0) + 1
                occurred_at = datetime.now(timezone.utc)
                event_id = f"event:{uuid.uuid4().hex}"
                facts = {
                    "event_id": event_id,
                    "execution_id": execution_id,
                    "invocation_id": invocation_id,
                    "tool_id": tool_id,
                    "sequence": sequence,
                    "occurred_at": occurred_at.isoformat(),
                    "effect_type": effect_type.value,
                    "source_resource": source_resource,
                    "destination_resource": destination_resource,
                    "classification": classification.value,
                    "operation": operation,
                    "outcome": outcome,
                    "metadata": safe_meta,
                }
                evidence_ref = self._evidence_store.create("observed_effect", facts)
                event = ObservedEffect(
                    event_id=event_id, execution_id=execution_id,
                    invocation_id=invocation_id, tool_id=tool_id, sequence=sequence,
                    occurred_at=occurred_at, effect_type=effect_type,
                    source_resource=source_resource, destination_resource=destination_resource,
                    classification=classification, operation=operation, outcome=outcome,
                    evidence=[evidence_ref], metadata=safe_meta,
                )
                event_copy = event.model_copy(deep=True)
                self._events.setdefault(execution_id, []).append(event)
                self._sequences[execution_id] = sequence
                return event_copy
            except RecorderUnavailable:
                raise
            except Exception as exc:
                raise RecorderUnavailable("RECORDER_RECORD_FAILED") from exc

    def events_for(self, execution_id: str) -> list[ObservedEffect]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._events.get(execution_id, [])]

    def evidence_resolves(self, execution_id: str) -> bool:
        try:
            for event in self.events_for(execution_id):
                if not all(self._evidence_store.verify(ref) for ref in event.evidence):
                    return False
            return True
        except Exception:
            return False
