"""Controlled policy-vector operations for the R5 local backend."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.rag.documents import ParsedPolicyDocument, parse_policy_document
from app.rag.store import PolicyRAGStore


class PolicyVectorService:
    def __init__(self, store: PolicyRAGStore, approved_directory: str | Path) -> None:
        self.store = store
        self.approved_directory = Path(approved_directory).expanduser().resolve()

    def index_approved_file(self, relative_path: str) -> dict[str, Any]:
        document = self.prepare_approved_file(relative_path)
        return self.ingest_prepared(document)

    def prepare_approved_file(self, relative_path: str) -> ParsedPolicyDocument:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("A policy path relative to the approved directory is required")
        root = self.approved_directory
        path = (root / relative_path).resolve()
        if root not in path.parents or path.suffix.lower() not in {".md", ".markdown", ".txt"}:
            raise ValueError("Policy path must be a Markdown or text file under the approved directory")
        document = parse_policy_document(path)
        if document.metadata.document_status != "ACTIVE":
            raise ValueError("Only ACTIVE policy documents may be indexed")
        return document

    def ingest_prepared(self, document: ParsedPolicyDocument) -> dict[str, Any]:
        result = self.store.ingest_document(document)
        metadata = document.metadata.model_dump(mode="json")
        metadata["content_sha256"] = document.content_sha256
        return {"document_id": result.document_id, "version": result.version,
                "chunks_written": result.chunks_written,
                "obsolete_chunks_deleted": result.obsolete_chunks_deleted,
                "skipped_unchanged": result.skipped_unchanged, "metadata": metadata}

    def get_document_metadata(self, document_id: str) -> dict[str, Any] | None:
        rows = self.store.collection.get(where={"document_id": {"$eq": document_id}},
                                         include=["metadatas"])
        metadata = list(rows.get("metadatas") or [])
        return dict(metadata[0]) if metadata else None

    def deactivate(self, document_id: str) -> dict[str, Any]:
        count, metadata = self.store.deactivate_document(document_id)
        if metadata is None:
            raise KeyError("Policy document not found in vector index")
        return {"document_id": document_id, "chunks_deactivated": count,
                "version": metadata.get("version"), "source": metadata.get("source"),
                "access_classification": metadata.get("access_classification"),
                "content_sha256": metadata.get("content_sha256"),
                "document_status": "OBSOLETE", "metadata": metadata}
