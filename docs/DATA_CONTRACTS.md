# Data Contracts (R1)

The source-of-truth validation models live in `app/core/schemas/contracts.py` and use the Pydantic version already available through the existing FastAPI environment. JSON Schema snapshots are generated from the models into `app/core/schemas/json/`; regenerate them with `python -m app.core.schemas.export_json_schemas` after an approved contract change. No runtime service or database is introduced by these schemas.

## Key contract rules

1. Tool manifests separate `declared_capabilities`, `declared_effects`, and `permission_scope`; allowed resources/destinations are explicit.
2. Every observed effect requires `event_id`, `execution_id`, `invocation_id`, `tool_id`, positive sequence, timestamp, operation, outcome, classification, and at least one non-LLM evidence reference.
3. Graph edges require event IDs and evidence IDs and are bound to an execution. A capability path is ordered and event-backed.
4. A COMPLETE coverage claim requires a non-empty explicit scope and no known gaps within that declared scope. COMPLETE does not mean system-wide completeness.
5. CONFIRMED_VIOLATION findings require a policy rule ID, event IDs, and a path. A deterministic condition must be demonstrated separately.
6. Absence of a violation supports only INCONCLUSIVE for PARTIAL, FAILED, or UNKNOWN coverage. COMPLETE permits only the bounded status NO_VIOLATION_OBSERVED.
7. VERIFIED remediation status requires at least one verification run ID; verification records themselves need execution IDs and evidence IDs.
8. Unknown fields are rejected; timestamps are timezone-aware by contract intention and should be UTC at ingestion.

## R4 correction: events and graph relationships are distinct

`EffectType` represents operations actually recorded by an instrumented adapter; `GraphEdgeType` represents relationships used only to connect graph nodes. `USES` belongs to `GraphEdgeType` and is not an observed operation. R4 removes `USES` from the observed-event enum and serializes `GraphEdge.edge_type` with the same historical wire label through `GraphEdgeType`, preserving graph-edge values and R0–R3 observed R2 records. No R2 adapter ever emitted a `USES` effect. `GraphEdge.invocation_ids` remains an optional field with an empty default for older records. Decision D-027 records this correction to historical R3 design decision D-021.

## JSON Schema generation
JSON schemas use the JSON Schema dialect emitted by Pydantic. Enum sets and required fields are machine readable. Cross-record invariants—such as edge endpoints existing in the same graph, policy applicability, or event IDs actually existing in a database—cannot be established by a single JSON Schema and must be enforced by service/database logic and integration tests.

## R4 RAG document/chunk metadata

`app/rag/documents.py` and `app/rag/store.py` implement local Markdown/TXT ingestion, stable chunk IDs, `document_id`, `version`, relative `source`, `section`, optional `page`, language, optional `policy_id`, access classification, active/obsolete status, and content/chunk hashes. Query metadata filters enforce the caller's clearance and exclude obsolete documents before vector ranking. Re-indexing a changed version removes stale chunks for that document; deletion APIs can remove one version or retain a selected version. Every returned passage carries source metadata for citations. Structured `PolicyRule` values are loaded separately from the trusted local catalog; retrieved natural-language passages are untrusted evidence/context and cannot define or modify executable rules.

## Limits
The current models are design/validation contracts, not a complete immutable event store, authentication system, policy engine, or production API. No third-party package was installed for R1.
