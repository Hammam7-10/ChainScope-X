"""In-memory store for sanitized, deterministic local test evidence."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.schemas.contracts import EvidenceReference


class EvidenceIntegrityError(RuntimeError):
    pass


_FORBIDDEN_KEYS = {"content", "payload", "raw_input", "document_text", "query", "secret", "token"}


def _reject_payload_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise ValueError(f"Evidence may not store payload field: {key}")
            _reject_payload_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_payload_fields(child)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    canonical_payload: str
    sha256: str
    recorded_at: datetime

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload)


class EvidenceStore:
    """Evidence references resolve only to records actually held in this local store."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        self._lock = threading.RLock()

    def create(self, kind: str, payload: dict[str, Any]) -> EvidenceReference:
        if not kind.strip():
            raise ValueError("Evidence kind is required")
        _reject_payload_fields(payload)
        canonical = _canonical_json(payload)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        evidence_id = f"evidence:{uuid.uuid4().hex}"
        record = EvidenceRecord(evidence_id, kind, canonical, digest, now)
        with self._lock:
            self._records[evidence_id] = record
        return EvidenceReference(evidence_id=evidence_id, kind=kind, sha256=digest,
                                 recorded_at=now, uri=None, llm_generated=False)

    def resolve(self, evidence_id: str) -> EvidenceRecord:
        with self._lock:
            try:
                return self._records[evidence_id]
            except KeyError as exc:
                raise KeyError(f"Evidence reference does not resolve: {evidence_id}") from exc

    def verify(self, reference: EvidenceReference) -> bool:
        try:
            record = self.resolve(reference.evidence_id)
        except KeyError:
            return False
        actual = hashlib.sha256(record.canonical_payload.encode("utf-8")).hexdigest()
        return (record.sha256 == actual == reference.sha256
                and record.kind == reference.kind
                and record.recorded_at == reference.recorded_at)

    def count(self) -> int:
        with self._lock:
            return len(self._records)
