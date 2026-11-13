"""Persistent local Chroma store with version replacement and attributed retrieval."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.schemas.contracts import Classification
from app.rag.documents import ParsedPolicyDocument, chunk_policy_document, parse_policy_document
from app.rag.embeddings import FastEmbedEncoder, default_encoder


_CLASSIFICATION_ORDER = (
    Classification.PUBLIC,
    Classification.INTERNAL,
    Classification.CONFIDENTIAL,
    Classification.RESTRICTED,
)


@dataclass(frozen=True)
class RetrievedPassage:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    distance: float


@dataclass(frozen=True)
class IngestReport:
    document_id: str
    version: str
    chunks_written: int
    obsolete_chunks_deleted: int
    skipped_unchanged: bool = False


class PolicyRAGStore:
    """Local-only Chroma persistence; caller supplies locally generated embeddings."""

    COLLECTION_NAME = "chainscope_policy_documents"

    def __init__(self, persist_directory: str | Path | None = None, *,
                 encoder: FastEmbedEncoder | None = None,
                 collection_name: str = COLLECTION_NAME) -> None:
        root = Path(__file__).resolve().parents[2]
        if persist_directory is None:
            persist_directory = os.getenv("CHAIN_SCOPE_CHROMA_DIR", str(root / "data" / "chroma"))
        self.persist_directory = Path(persist_directory).expanduser().resolve()
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.encoder = encoder or default_encoder()
        try:
            import chromadb
            from chromadb.config import Settings
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False),
            )
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
        except Exception as exc:
            raise RuntimeError("Persistent Chroma collection could not be initialized") from exc

    def ingest_file(self, path: str | Path) -> IngestReport:
        document = parse_policy_document(path)
        return self.ingest_document(document)

    def ingest_document(self, document: ParsedPolicyDocument) -> IngestReport:
        chunks = chunk_policy_document(document)
        if not chunks:
            raise ValueError("Policy document has no indexable text")
        if len(chunks) > 5_000:
            raise ValueError("Policy document exceeds the bounded 5,000-chunk ingestion limit")
        new_ids = [chunk.chunk_id for chunk in chunks]
        old = self.collection.get(
            where={"document_id": document.metadata.document_id},
            include=["metadatas"],
        )
        old_ids = list(old.get("ids") or [])
        old_metadatas = list(old.get("metadatas") or [])
        unchanged = (bool(old_ids) and set(old_ids) == set(new_ids)
                     and len(old_ids) == len(old_metadatas) and all(
            metadata.get("version") == document.metadata.version
            and metadata.get("content_sha256") == document.content_sha256
            and metadata.get("document_status") == document.metadata.document_status
            for metadata in old_metadatas
        ))
        if unchanged:
            return IngestReport(document.metadata.document_id, document.metadata.version,
                                len(old_ids), 0, True)

        vectors = self.encoder.encode([chunk.text for chunk in chunks])
        self.collection.upsert(
            ids=new_ids,
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata for chunk in chunks],
        )
        stale_ids = [item for item in old_ids if item not in set(new_ids)]
        if stale_ids:
            self.collection.delete(ids=stale_ids)
        return IngestReport(document.metadata.document_id, document.metadata.version,
                            len(new_ids), len(stale_ids), False)

    def sync_directory(self, directory: str | Path) -> tuple[IngestReport, ...]:
        root = Path(directory)
        if not root.is_dir():
            raise FileNotFoundError("Policy document directory does not exist")
        paths = sorted(path for path in root.rglob("*")
                       if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"})
        reports = [self.ingest_file(path) for path in paths]
        return tuple(reports)

    def delete_document_version(self, document_id: str, version: str) -> int:
        rows = self.collection.get(
            where={"$and": [
                {"document_id": {"$eq": document_id}},
                {"version": {"$eq": version}},
            ]},
            include=["metadatas"],
        )
        ids = list(rows.get("ids") or [])
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def delete_obsolete_versions(self, document_id: str, *, keep_version: str) -> int:
        rows = self.collection.get(where={"document_id": {"$eq": document_id}},
                                   include=["metadatas"])
        ids = list(rows.get("ids") or [])
        metadatas = list(rows.get("metadatas") or [])
        obsolete = [chunk_id for chunk_id, metadata in zip(ids, metadatas)
                    if metadata.get("version") != keep_version]
        if obsolete:
            self.collection.delete(ids=obsolete)
        return len(obsolete)

    def retrieve(self, query: str, *, clearance: Classification = Classification.INTERNAL,
                 top_k: int = 4) -> tuple[RetrievedPassage, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("RAG query must be non-empty text")
        if not isinstance(clearance, Classification):
            clearance = Classification(clearance)
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be within 1..10")
        total = self.collection.count()
        if total == 0:
            return ()
        query_vector = self.encoder.encode([query])[0]
        clearance_index = _CLASSIFICATION_ORDER.index(clearance)
        visible_labels = [item.value for item in _CLASSIFICATION_ORDER[:clearance_index + 1]]
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, total),
            where={"$and": [
                {"document_status": {"$eq": "ACTIVE"}},
                {"access_classification": {"$in": visible_labels}},
            ]},
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        passages = [RetrievedPassage(
            chunk_id=chunk_id,
            text=text,
            metadata=dict(metadata),
            distance=float(distance),
        ) for chunk_id, text, metadata, distance in zip(ids, docs, metadatas, distances)]
        return tuple(passages)

    def count(self) -> int:
        return int(self.collection.count())
