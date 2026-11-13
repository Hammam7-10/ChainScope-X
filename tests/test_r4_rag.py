"""R4 RAG tests exercise real FastEmbed vectors and persistent Chroma, not keyword mocks."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.core.schemas.contracts import Classification
from app.rag.documents import chunk_policy_document, parse_policy_document
from app.rag.store import PolicyRAGStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = PROJECT_ROOT / "data" / "policies"


class RAGDocumentTests(unittest.TestCase):
    def test_document_metadata_section_and_page_survive_chunking(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.md"
            path.write_text(
                '+++\ndocument_id="DOC-QA-1"\nversion="1.0"\nsource="qa/policy.md"\n'
                'language="en"\npolicy_id="POL-QA-1"\naccess_classification="INTERNAL"\n'
                'document_status="ACTIVE"\npage=7\n+++\n# Retention\n'
                + ("Keep event provenance and evidence references for review. " * 35),
                encoding="utf-8",
            )
            parsed = parse_policy_document(path)
            chunks = chunk_policy_document(parsed, max_words=20, overlap_words=4)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["document_id"], "DOC-QA-1")
        self.assertEqual(chunks[0].metadata["version"], "1.0")
        self.assertEqual(chunks[0].metadata["source"], "qa/policy.md")
        self.assertEqual(chunks[0].metadata["section"], "Retention")
        self.assertEqual(chunks[0].metadata["page"], 7)
        self.assertEqual(chunks[0].metadata["policy_id"], "POL-QA-1")
        self.assertEqual(chunks[0].metadata["access_classification"], "INTERNAL")
        self.assertTrue(chunks[0].metadata["chunk_id"].startswith("chunk:"))
        self.assertEqual(chunks[0].metadata["language"], "en")

    def test_source_path_rejects_absolute_and_traversal_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unsafe.md"
            path.write_text(
                '+++\ndocument_id="DOC-UNSAFE"\nversion="1"\nsource="../../secret.txt"\n+++\nText',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                parse_policy_document(path)


class ChromaRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = PolicyRAGStore(persist_directory=PROJECT_ROOT / "data" / "chroma")
        cls.sync_reports = cls.store.sync_directory(POLICY_DIR)

    def test_real_multilingual_semantic_retrieval_returns_citations(self):
        english = self.store.retrieve(
            "confidential file sharing to prohibited simulated external destination",
            clearance=Classification.INTERNAL,
            top_k=2,
        )
        arabic = self.store.retrieve(
            "ما متطلبات اكتمال الرصد والتغطية الجزئية؟",
            clearance=Classification.INTERNAL,
            top_k=2,
        )
        self.assertTrue(english)
        self.assertTrue(arabic)
        self.assertEqual(english[0].metadata["document_id"], "DOC-CONFIDENTIAL-EXTERNAL-001")
        self.assertEqual(arabic[0].metadata["document_id"], "DOC-MONITORING-COMPLETENESS-001")
        for result in (english[0], arabic[0]):
            self.assertTrue(result.metadata["source"].startswith("policy/"))
            self.assertTrue(result.metadata["chunk_id"])
            self.assertGreaterEqual(result.distance, 0.0)
            self.assertLess(result.distance, 1.0)

    def test_access_classification_filter_excludes_restricted_context(self):
        low_clearance = self.store.retrieve(
            "restricted synthetic fixture classification access", clearance=Classification.PUBLIC, top_k=10)
        high_clearance = self.store.retrieve(
            "restricted synthetic fixture classification access", clearance=Classification.RESTRICTED, top_k=10)
        self.assertNotIn("DOC-RESTRICTED-ACCESS-001",
                         {item.metadata["document_id"] for item in low_clearance})
        self.assertIn("DOC-RESTRICTED-ACCESS-001",
                      {item.metadata["document_id"] for item in high_clearance})

    def test_repeated_sync_is_idempotent(self):
        before = self.store.count()
        reports = self.store.sync_directory(POLICY_DIR)
        self.assertEqual(before, self.store.count())
        self.assertTrue(reports)
        self.assertTrue(all(item.skipped_unchanged for item in reports))

    def test_version_update_replaces_obsolete_chunks_and_supports_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "versioned.md"
            db = root / "chroma"
            def write_version(version: str, paragraph: str):
                path.write_text(
                    f'+++\ndocument_id="DOC-VERSION-QA"\nversion="{version}"\n'
                    'source="qa/versioned.md"\nlanguage="en"\n'
                    'access_classification="INTERNAL"\ndocument_status="ACTIVE"\n+++\n'
                    f'# Version test\n{paragraph}\n', encoding="utf-8")
            write_version("1.0", "obsolete alpha retention procedure")
            store = PolicyRAGStore(db, collection_name="version_update_test")
            first = store.ingest_file(path)
            self.assertGreater(first.chunks_written, 0)
            write_version("2.0", "current beta transmission prohibition")
            second = store.ingest_file(path)
            self.assertEqual(second.version, "2.0")
            rows = store.collection.get(where={"document_id": "DOC-VERSION-QA"}, include=["metadatas"])
            versions = {item["version"] for item in rows["metadatas"]}
            self.assertEqual(versions, {"2.0"})
            self.assertGreater(second.obsolete_chunks_deleted, 0)
            removed = store.delete_document_version("DOC-VERSION-QA", "2.0")
            self.assertGreater(removed, 0)
            self.assertEqual(store.collection.get(where={"document_id": "DOC-VERSION-QA"})["ids"], [])

    def test_persistent_chroma_collection_is_retrievable_after_process_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "restart.md"
            source.write_text(
                '+++\ndocument_id="DOC-RESTART-QA"\nversion="3.1"\n'
                'source="qa/restart.md"\nlanguage="en"\n'
                'access_classification="INTERNAL"\ndocument_status="ACTIVE"\n+++\n'
                '# Restart persistence\nPersistent vector index survives a fresh process and preserves source attribution.\n',
                encoding="utf-8",
            )
            db_path = root / "persistent_chroma"
            store = PolicyRAGStore(db_path, collection_name="restart_persistence_test")
            store.ingest_file(source)
            query_vector = store.encoder.encode(["persistent vector index after process restart"])[0]
            vector_file = root / "query_vector.json"
            vector_file.write_text(json.dumps(query_vector), encoding="utf-8")
            script = r'''
import json, sys
import chromadb
from chromadb.config import Settings
client = chromadb.PersistentClient(path=sys.argv[1], settings=Settings(anonymized_telemetry=False))
collection = client.get_collection(name="restart_persistence_test", embedding_function=None)
vector = json.load(open(sys.argv[2], encoding="utf-8"))
result = collection.query(query_embeddings=[vector], n_results=1,
    where={"$and":[{"document_status":{"$eq":"ACTIVE"}},
                    {"access_classification":{"$in":["PUBLIC","INTERNAL"]}}]},
    include=["documents","metadatas","distances"])
assert result["metadatas"][0][0]["document_id"] == "DOC-RESTART-QA"
assert result["metadatas"][0][0]["source"] == "qa/restart.md"
print("PERSISTED_RETRIEVAL_OK")
'''
            env = dict(os.environ)
            env["PYTHONPATH"] = str(PROJECT_ROOT)
            child = subprocess.run(
                [sys.executable, "-c", script, str(db_path), str(vector_file)],
                cwd=PROJECT_ROOT, env=env, check=True, capture_output=True, text=True, timeout=60,
            )
            self.assertIn("PERSISTED_RETRIEVAL_OK", child.stdout)


if __name__ == "__main__":
    unittest.main()
