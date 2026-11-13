# R5 Backend Persistence Specification

## Objective and scope

R5 adds a local-development persistence/API vertical slice on top of the accepted R4 workflow. It does not replace the R2 synthetic adapters, R3 deterministic verdict engine, or R4 planning/RAG pipeline. The API invokes `ChainScopeWorkflow` once for a bounded `AgentRequest`; only the existing R3 `AnalysisService` produces security findings/verdicts.

## Storage responsibilities

- **PostgreSQL** (`SQLAlchemy 2.x`, asyncpg, Alembic): `analysis_runs`, `findings`, `evidence_references`, `finding_evidence_links`, `policy_documents`. Relational identifiers, lifecycle/status, classification, severity, digest and indexed provenance fields are native columns. Validated R3 payloads and bounded metadata use JSON/JSONB.
- **MongoDB** (`PyMongo Async`): structured `execution_events` and sanitized `evidence_documents`. Stable keys are `run_id:event_id` and `run_id:evidence_id`; writes are upserts. Queries are paginated and use run/execution/provenance indexes.
- **Chroma**: local vector index for policy chunks only. It remains distinct from MongoDB. R5 exposes controlled index/re-index, OBSOLETE marking and clearance-filtered search operations.

The initial schema is a versioned Alembic migration. The service does not silently create tables on startup. The application connects only from explicit environment values; `.env.example` leaves DSNs empty.

## Run lifecycle and cross-store consistency

1. The API validates `AgentRequest`; create a PostgreSQL `RUNNING` row with scenario/mode/clearance, query digest and character count. Raw query text is not stored.
2. Run the R4 graph in a worker thread. The graph remains bounded and uses only its approved synthetic tools.
3. Prepare a sanitized R4 report and structured event/evidence documents. Remove the raw query and all retrieved policy excerpts from the persisted report; retain policy source citations and R3 finding details.
4. In one PostgreSQL transaction, stage the report plus an idempotent Mongo retry snapshot and move the run to `PERSISTENCE_PENDING`.
5. Upsert events/evidence in Mongo. Then commit indexed findings, evidence references/links, sanitized report and final run status in PostgreSQL, clearing the retry snapshot.
6. If the Mongo write or SQL finalization fails, the run remains `PERSISTENCE_PENDING`. Replaying `/reconcile` repeats Mongo upserts safely then finalizes relational rows. This is an explicit saga/reconciliation design, not a distributed ACID claim.

The finding/evidence composite keys prevent a finding from resolving evidence attached to a different run. Evidence SHA-256 values are integrity digests over canonical sanitized evidence facts, not proof of source truth by themselves.

## API and policy operations

Endpoints are listed in `API_CONTRACTS.md`. Requests use existing Pydantic contracts, bounded pagination and safe errors. Policy index paths are resolved and constrained below the approved policy directory; only ACTIVE Markdown/TXT documents can be newly indexed. Before a re-index/deactivation changes Chroma, PostgreSQL records `INDEXING_PENDING` or `DEACTIVATION_PENDING`; analysis and policy search are blocked until the operation reaches a final state. Deactivation sets Chroma chunk status to OBSOLETE and keeps provenance rather than deleting it. The R5 workflow filters OBSOLETE documents out of trusted R3 rules and reapplies that state after R4 source synchronization; active-status/classification retrieval filters remain enforced.

## Privacy and security boundary

R5 is a development-only local API, not an authenticated production backend. It refuses its API group unless `APP_ENV` is development/test and the configured bind `HOST` is loopback. No identity, tenant/role authorization, rate limiting, production secret management, CSRF/session, public CORS policy or dashboard is claimed. Bind only to `127.0.0.1`.

The API stores only a SHA-256 and character count for the query. Retrieved policy excerpts are stripped from the durable report. R2's evidence store rejects payload/content/query/secret keys; R5 verifies each evidence digest before writing. Do not persist credentials, raw tool arguments, user documents or arbitrary binaries. Retention/erasure workflows and production data classification are future work.

PostgreSQL and MongoDB are separate services and their writes are not atomic together. Policy update across Chroma and PostgreSQL is likewise not atomic; a metadata write failure must be treated as incomplete and retried/reconciled, never assumed successful. Errors returned by the API avoid driver messages and credentials.

## Validation and limitations

R5 automated tests use actual SQLAlchemy models/repository with an in-memory SQLite dialect and fake Mongo wire interfaces for deterministic unit tests. A separate opt-in live integration test exercises actual PostgreSQL and MongoDB when dedicated `*_test` database DSNs are supplied and the migration has been applied. No live PostgreSQL or MongoDB service is available in the current build environment, so no live-database integration result is claimed.

The current environment is ARM64/Python 3.12.3. Compatible ARM64 wheels were resolved for asyncpg and PyMongo in this environment. The target Samsung Galaxy Tab S7+ / Debian PRoot and the stated Python 3.13.5 target remain untested. No DB server, Docker daemon, paid service, system package, or external database was provisioned as part of R5.
