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

## R3 additive graph-edge semantic

R3 adds the existing graph relationship value `USES` to the shared `EffectType` enum because `GraphEdge.edge_type` already uses that contract and R1 lineage semantics require explicit `USES` edges. This is additive: no prior enum value or observed R2 event was changed, and the six R2 adapters continue emitting only their established event effects. `GraphEdge.invocation_ids` is likewise an optional additive field with an empty default for older records.

## JSON Schema generation
JSON schemas use the JSON Schema dialect emitted by Pydantic. Enum sets and required fields are machine readable. Cross-record invariants—such as edge endpoints existing in the same graph, policy applicability, or event IDs actually existing in a database—cannot be established by a single JSON Schema and must be enforced by service/database logic and integration tests.

## Future RAG document/chunk metadata
Every indexed chunk should retain `document_id`, `version`, `source`, `section`, optional `page`, stable `chunk_id`, `language` (BCP-47 tag, including Arabic and English variants), `effective_date`, `status`, `access_classification`, related `policy_id`, and content hash. Ingestion must preserve access rules and version provenance; retrieval results must return these references so text remains attributable. Updating a version must not silently erase prior source attribution; authorized deletion is explicit and auditable. Retrieved text is untrusted input and cannot override application security rules. These are a future metadata contract only; RAG and embeddings are not implemented in R1.

## Limits
The current models are design/validation contracts, not a complete immutable event store, authentication system, policy engine, or production API. No third-party package was installed for R1.
