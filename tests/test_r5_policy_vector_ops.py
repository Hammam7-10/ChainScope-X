from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.policy_service import PolicyVectorService
from app.rag.store import IngestReport, PolicyRAGStore


def _policy_text(status="ACTIVE"):
    return f'''+++\ndocument_id = "TEST-POLICY-001"\nversion = "1.0"\nsource = "policy/test.md"\nlanguage = "en"\naccess_classification = "INTERNAL"\ndocument_status = "{status}"\n+++\n# Test policy\n\nOnly a synthetic sample policy.\n'''


class FakeIngestStore:
    def __init__(self):
        self.ingested = []

    def ingest_document(self, document):
        self.ingested.append(document)
        return IngestReport(document.metadata.document_id, document.metadata.version, 1, 0)

    def deactivate_document(self, document_id):
        return 2, {"document_id": document_id, "version": "1.0", "source": "policy/test.md",
                    "access_classification": "INTERNAL", "content_sha256": "f" * 64}


class FakeCollection:
    def __init__(self):
        self.updated = None

    def get(self, where, include):
        assert where["document_id"]["$eq"] == "TEST-POLICY-001"
        return {"ids": ["chunk:1", "chunk:2"],
                "metadatas": [{"document_id": "TEST-POLICY-001", "document_status": "ACTIVE",
                               "version": "1.0"},
                              {"document_id": "TEST-POLICY-001", "document_status": "ACTIVE",
                               "version": "1.0"}]}

    def update(self, *, ids, metadatas):
        self.updated = (ids, metadatas)


def test_policy_index_accepts_only_active_files_inside_approved_root(tmp_path):
    root = tmp_path / "policies"
    root.mkdir()
    (root / "safe.md").write_text(_policy_text(), encoding="utf-8")
    (root / "inactive.md").write_text(_policy_text("OBSOLETE"), encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text(_policy_text(), encoding="utf-8")
    store = FakeIngestStore()
    service = PolicyVectorService(store, root)

    result = service.index_approved_file("safe.md")
    assert result["document_id"] == "TEST-POLICY-001"
    assert result["chunks_written"] == 1
    assert len(store.ingested) == 1
    with pytest.raises(ValueError, match="ACTIVE"):
        service.index_approved_file("inactive.md")
    with pytest.raises(ValueError, match="under the approved directory"):
        service.index_approved_file("../outside.md")
    with pytest.raises(ValueError):
        service.index_approved_file(str(outside))


def test_chroma_deactivation_marks_chunks_obsolete_without_deleting_them():
    store = PolicyRAGStore.__new__(PolicyRAGStore)
    collection = FakeCollection()
    store.collection = collection
    count, metadata = store.deactivate_document("TEST-POLICY-001")
    assert count == 2
    assert metadata["document_status"] == "OBSOLETE"
    assert collection.updated[0] == ["chunk:1", "chunk:2"]
    assert all(item["document_status"] == "OBSOLETE" for item in collection.updated[1])
