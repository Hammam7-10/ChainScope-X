# Relational Database Schema (R1 design only)

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

## SQL/NoSQL question
Open academic decision: PostgreSQL JSONB plus ChromaDB may not satisfy a rubric requiring an independent document-oriented NoSQL store. Verify the exact rubric. Do not add MongoDB or another database without Project Director approval. Chroma is the vector index, not assumed to be a general document database.
