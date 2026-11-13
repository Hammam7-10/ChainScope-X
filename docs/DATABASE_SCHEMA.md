# Relational Database Schema (R1 logical design and R5 implementation)

PostgreSQL is the future relational source of truth. This document defines a logical design; no database was connected and no migration was created in R1. Use UUID primary keys (or stable text IDs where domain identities must remain human-readable), `created_at`/`updated_at` as `timestamptz`, foreign keys with deliberate deletion behavior, CHECK constraints for enums/status transitions, and JSONB only for validated schemas/payloads rather than unindexed core relations.

## Relations and key columns

| Table | Primary / foreign keys and purpose |
|---|---|
| users | `user_id`; auth subject unique, active flag. |
| roles | `role_id`; unique role name. |
| user_roles | PK (`user_id`,`role_id`); FKs users/roles. |
| tools | `tool_id`; stable unique key, status. |
| tool_versions | `tool_version_id`; FK tools, unique (`tool_id`,`version`), schemas JSONB, description. |
| declared_capabilities | PK `capability_id`; FK tool_version_id, capability key. |
| declared_effects | PK `declared_effect_id`; FK tool_version_id, effect type/resource scopes. |
| assets | `asset_id`; stable resource key, owner metadata. |
| asset_classifications | PK `classification_id`; FK asset_id, label, effective interval and source. |
| destinations | `destination_id`; stable destination key, class, external flag. |
| policies | `policy_id`; stable identifier, lifecycle/status. |
| policy_versions | `policy_version_id`; FK policy_id, unique version, structured rule JSONB, effective dates, source document reference. |
| test_scenarios | `scenario_id`; ground-truth label, fixture references, expected behavior. |
| test_campaigns | `campaign_id`; creator FK, status, configuration JSONB. |
| execution_runs | `execution_id`; optional campaign/scenario FKs, start/end, outcome, coverage summary. |
| tool_invocations | `invocation_id`; FK execution_id, tool_version_id, sequence, inputs/outputs by protected reference, outcome. |
| observed_effects | `event_id`; FKs execution_id/invocation_id/tool_id, unique (`execution_id`,`sequence`), effect, resource IDs, classification, evidence JSONB/reference. |
| instrumentation_coverage | `coverage_id`; unique FK execution_id, status, monitored scope/gaps JSONB, recorder version. |
| capability_nodes | `node_id`; execution FK nullable only for catalog nodes, type/resource identity. |
| capability_edges | `edge_id`; FK source/target nodes and execution, event IDs via join table. |
| edge_events | PK (`edge_id`,`event_id`); FKs capability_edges/observed_effects. |
| findings | `finding_id`; execution FK, optional policy-version FK, type/assessment/severity/status/uncertainty JSONB. |
| finding_events | PK (`finding_id`,`event_id`); evidence linkage. |
| finding_paths | `finding_path_id`; FK finding_id; ordered node/edge/event reference representation. |
| remediation_candidates | `remediation_id`; FK finding_id, type/target/status/criteria. |
| remediation_plans | `plan_id`; owner/auditor FKs, selected restrictions and approval lifecycle. |
| verification_runs | `verification_run_id`; FK remediation_id, execution IDs via join, outcomes/evidence. |
| verification_executions | PK (`verification_run_id`,`execution_id`); FKs both. |
| audit_logs | `audit_id`; actor FK nullable for system events, action/resource/time, redacted metadata JSONB. |
| stored_files | `stored_file_id`; owner FK, private storage key, type/size/hash/classification; never public URL as primary identity. |

## Constraints and indexes
Use FK constraints for every relationship; prevent deleting evidence-bearing executions/events while findings or verifications refer to them (RESTRICT or soft-delete). `observed_effects` require non-empty IDs/outcome/effect and valid classification. Enforce unique tool version, policy version, and event sequence within execution. Constrain coverage status and finding/remediation statuses. Check effective date intervals. Index observed effects by `(execution_id, sequence)`, `(tool_id, occurred_at)`, effect type, source/destination resource; findings by `(status,severity,created_at)` and policy version; edges by source/target and execution; active/effective policies; campaign/run relationships. Add GIN indexes only for demonstrably queried JSONB metadata.

## Transactions and tenant scope
Create an execution, coverage record, invocations/events and resulting graph/findings in explicit transactions where atomic consistency is required; retain immutable provenance. Future Supabase Row Level Security should use authenticated tenant/user ownership with least privilege; service credentials remain server-side. No RLS implementation or CRUD claim is made in R1.

## SQL/NoSQL question (R1 historical decision)
At R1, PostgreSQL JSONB plus ChromaDB might not satisfy a rubric requiring an independent document-oriented NoSQL store; MongoDB was correctly withheld pending approval. The question was later resolved by explicit R5 approval D-032/D-033: the MongoDB document store is implemented below. Chroma remains the policy vector index, not the independent document database.

## R5 implementation

R5 adds a concrete Alembic migration at `alembic/versions/20261114_01_r5_persistence.py` (revision `20261114_01`). The following tables and document stores are implemented; the earlier R1 logical catalog remains preserved above. Apply migrations explicitly with `alembic upgrade head`; application startup never creates or migrates tables automatically.

## Implemented PostgreSQL records

| Table | R5 role and key fields |
|---|---|
| `analysis_runs` | Primary key `run_id`; unique nullable `execution_id`; `scenario_id`, `status`, `workflow_status`, planner mode, redacted request metadata, sanitized result JSON, temporary retry snapshot, safe error codes, UTC start/completion times. |
| `findings` | Primary key `finding_id`; FK `run_id`; execution/type/assessment/severity/classification/status plus validated R3 finding payload. Indexes support run, severity, assessment, status and classification lookups. |
| `evidence_references` | Composite PK (`run_id`,`evidence_id`); FK to analysis run; kind, SHA-256, time, classification and optional source-document reference. Evidence bytes/content are not stored in PostgreSQL. |
| `finding_evidence_links` | Composite PK (`finding_id`,`evidence_id`); composite FKs require the finding and evidence to belong to the same run. |
| `policy_documents` | Primary key `document_id`; active/obsolete version, classification, portable source attribution, content digest and structured metadata. Policy text/vectors remain in the local Chroma index. |

PostgreSQL is authoritative for the relational run/finding/reference records. Validated report objects use JSON/JSONB alongside indexed relational columns; JSON is not used instead of run/finding/evidence relationships. The `retry_payload` field temporarily stores an idempotent persistence snapshot while a run is `PERSISTENCE_PENDING`; a successful finalization clears it. It contains structured sanitized effects/evidence but not the raw user query or policy excerpts.

## MongoDB document records

The independent MongoDB database contains two collections:

- `execution_events`: one document per observed effect, keyed by stable `run_id:event_id`, with run/execution/event identifiers, classification, explicit execution/invocation/tool/sequence provenance and the structured event.
- `evidence_documents`: one sanitized evidence record per evidence identifier, keyed by `run_id:evidence_id`, including kind, canonical payload, timestamp, classification where available and its SHA-256 integrity digest.

Writes use upserts and are idempotent. Indexes support run/sequence and execution/event lookups as well as evidence ID, digest and classification. MongoDB and PostgreSQL do not share a distributed ACID transaction: a SQL retry snapshot is retained in `PERSISTENCE_PENDING` if MongoDB fails; `POST /api/v1/analysis-runs/{run_id}/reconcile` replays the upserts and finalizes SQL. R3 remains the only authority for security findings.

The R2 evidence store rejects raw payload/content/query/secret fields. Before R5 persistence, the original request query is replaced by its SHA-256 digest and character count, and policy citation excerpts are removed. Do not add raw inputs, credentials, file contents or private user data to events/evidence. The application does not yet provide a retention schedule, tenant isolation, user identity, or deletion API.

## Indexing and operation

`PolicyRAGStore` remains a local Chroma vector index, not the document-oriented database. Controlled R5 operations index only ACTIVE Markdown/TXT policies below `CHAIN_SCOPE_POLICY_DIR`, re-index the same approved document deterministically, mark a policy OBSOLETE without destroying its provenance, and retrieve passages under the existing classification filter. PostgreSQL stores the policy metadata/digest; Chroma stores vectors, chunk metadata and policy text.

Connection details are supplied only by environment variables `CHAIN_SCOPE_POSTGRES_DSN`, `CHAIN_SCOPE_MONGODB_URI`, and `CHAIN_SCOPE_MONGODB_DATABASE`. `.env.example` keeps credential variables empty. SQLite/aiosqlite exists only in test dependencies for local relational unit tests; it is not a PostgreSQL substitute. The live integration suite uses only explicit `CHAIN_SCOPE_TEST_*` DSNs and is skipped when unavailable.

## Remaining logical design

The broader R1 academic design (users/roles, tools and versions, assets/classifications, campaigns, invocations, observed effects, coverage, graphs/paths, remediation/verification, audit logs and stored files) remains a future schema. R5 does not claim to implement those tables, authentication, tenant/RLS controls, a dashboard, real tools or remediation. Compatibility with Samsung Galaxy Tab S7+ / Debian PRoot remains pending direct target testing.
