# R4 RAG Specification

**Status:** Implemented in R4; local prototype, not a production knowledge service.

## Purpose and trust boundary

RAG supplies attributed policy/test context to the bounded agent. It does not execute policy. The authoritative policy catalog is parsed separately into typed `PolicyRule` models and evaluated deterministically by the R3 `AnalysisService`. Retrieved natural-language text is untrusted data: it cannot grant tools, modify policy, create evidence, or override the plan validator. The optional planner prompt explicitly labels retrieved passages untrusted; the deterministic scenario-document check provides a second gate before planning.

## Implementation

- Parser/chunker: `app/rag/documents.py` reads Markdown/TXT documents with TOML front matter and stable section-aware chunk IDs.
- Embeddings: `app/rag/embeddings.py` uses FastEmbed/ONNX locally with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions) [4] [5]. Cache defaults to `~/.cache/fastembed`; `FASTEMBED_CACHE_PATH` can override it. No hosted embedding endpoint is used.
- Store: `app/rag/store.py` uses ChromaDB `PersistentClient`, cosine distance, explicit caller-generated vectors, and disables Chroma anonymized telemetry [1] [2]. The default persistent path is `data/chroma`; `CHAIN_SCOPE_CHROMA_DIR` can override it.
- Source corpus: `data/policies/`; `CHAIN_SCOPE_POLICY_DIR` can override the location. Re-indexing is content/version aware and removes stale chunks for a changed source. The database, model cache, and generated scenario results are local and excluded from the source archive/Git history.

## Required metadata and version handling

Each chunk retains document ID, version, relative source, section, language, effective date, status, access classification, optional policy ID, chunk ID, and content SHA-256. The document parser rejects incomplete/invalid front matter. Unchanged content is skipped; changed content upserts stable IDs and removes stale IDs for the same document. Explicit helpers delete one document version or obsolete versions; deletion is not performed as a side effect of retrieval.

## Access filtering and retrieval

Clearance is an ordered lattice `PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED`. The Chroma query filters to `ACTIVE` documents whose classification is at or below the requester's clearance **before** vector ranking [3]. Top-k is bounded to 1..10; the agent uses top_k=4. Returned results include vector distance and source metadata for audit citations. The workflow requires a visible result for the scenario's designated policy document; empty or irrelevant retrieval stops planning and all tool execution.

R4 retrieval checks exercised Arabic and English queries against the real local embedding model. The Arabic monitoring query ranked `DOC-MONITORING-COMPLETENESS-001` first (cosine distance 0.3756); the English external-confidentiality query ranked `DOC-CONFIDENTIAL-EXTERNAL-001` first (0.2069); the workspace anomaly query ranked its corresponding policy first (0.2743). A PUBLIC-clearance query did not return a RESTRICTED fixture. Distances are observations from this small synthetic corpus, not quality guarantees or global thresholds.

## Resource and portability notes

The downloaded ONNX model blob is 235,052,644 bytes (~224 MiB); complete FastEmbed cache measured 241 MB. The selected model runs locally through ONNX Runtime without PyTorch [4] [5]. R4 dependency resolution was isolated in `.venv`; the observed host is Linux ARM64 / Python 3.12.3. Production startup on Android/Debian PRoot has **not** yet been tested. Offline startup requires the model cache to be provisioned in advance; otherwise the first model initialization may require network access.

## Limitations

The source corpus and Chroma collection are single-process prototype assets. There is no authentication service, tenant isolation, remote document ingestion, encryption-at-rest policy, database backup/restore automation, document signatures, or adversarial corpus pipeline. R4 does not validate semantic relevance at a general threshold; it enforces scenario-specific document presence only. Do not use this prototype for real secrets or production policy enforcement.

## Official implementation references

- Chroma and other package release metadata were checked against PyPI [8] [9] [10] [11]. LangGraph's StateGraph API is documented in [6]; the configured Groq model and JSON support are documented in [7] [12].

## References

[1]: https://docs.trychroma.com/docs/run-chroma/clients "Chroma persistent clients"
[2]: https://docs.trychroma.com/docs/embeddings/embedding-functions "Chroma embedding functions"
[3]: https://docs.trychroma.com/docs/querying-collections/metadata-filtering "Chroma metadata filtering"
[4]: https://qdrant.github.io/fastembed/examples/Supported_Models/ "FastEmbed supported models"
[5]: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 "Multilingual MiniLM model card"
[6]: https://docs.langchain.com/oss/python/langgraph/graph-api "LangGraph Graph API"
[7]: https://console.groq.com/docs/models "Groq supported models"
[8]: https://pypi.org/project/chromadb/ "ChromaDB on PyPI"
[9]: https://pypi.org/project/fastembed/ "FastEmbed on PyPI"
[10]: https://pypi.org/project/langgraph/ "LangGraph on PyPI"
[11]: https://pypi.org/project/groq/ "Groq Python SDK on PyPI"
[12]: https://console.groq.com/docs/model/openai/gpt-oss-20b "Groq GPT OSS 20B model"
