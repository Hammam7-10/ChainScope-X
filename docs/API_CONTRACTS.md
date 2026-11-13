# API Contracts — R1 logical design and R5 local backend

The resource catalog below preserves the broader R1 academic design. The implemented R5 API is listed separately. Every R5 business endpoint is available only in `APP_ENV=development|test` with a loopback `HOST` (`127.0.0.1`, `localhost`, or `::1`) and a direct loopback client peer; reverse proxies are unsupported. R5 has no user authentication, role system, tenant isolation or production authorization; it must not be bound to a public/network interface. `/health` remains a minimal liveness endpoint and does not claim dependency health.

## R1 logical resource catalog (future work)

| Group / routes | Intended request and response | Intended access |
|---|---|---|
| Tools: `GET/POST /api/tools`, `GET /api/tools/{id}` | `ToolManifest`; `{tool_id,version,manifest,created_at}`; paginated lists. | Viewer read; analyst create; admin manage. |
| Policies: `GET/POST /api/policies`, `POST /api/policies/{id}/versions` | Draft policy with structured `PolicyRule`, effective date, source and classification; activation audited. | Viewer read; analyst draft; admin activate. |
| Scenarios: `GET/POST /api/scenarios` | Fixture references and expected effects only; never arbitrary executable code. | Viewer read; analyst create. |
| Campaigns: `POST /api/campaigns`, `GET /api/campaigns/{id}` | Bounded scenario/tool selection and execution IDs. | Analyst create/run; viewer read. |
| Executions/effects: `POST /api/executions`, `GET /api/executions/{id}`, `GET /api/executions/{id}/effects` | Provenance-bearing run and observed effects; client-created effects are never recorder truth. | Analyst run; viewer read. |
| Findings/graph: `GET /api/findings`, `GET /api/findings/{id}`, `GET /api/executions/{id}/graph` | Finding, path, policy, coverage and evidence references; bounded graph query. | Viewer read; analyst annotate. |
| Remediation/verification: `POST /api/findings/{id}/remediations`, `POST /api/remediations/{id}/verification-runs` | Proposed constraints and bounded synthetic verification; VERIFIED only after criteria/evidence pass. | Analyst propose/run; admin approve/apply. |
| Dashboard: `GET /api/dashboard/summary` | Time-bounded metrics; unknown values remain unknown, not fabricated zero. | Viewer read. |

## Implemented R5 endpoints

| Method and path | Behavior |
|---|---|
| `GET /api/v1/health/dependencies` | PostgreSQL/Mongo dependency health when configured; otherwise returns `unconfigured`. Chroma is identified as local persistent storage, not a remote health check. |
| `POST /api/v1/analysis-runs` | Accepts the existing strict `AgentRequest` (`scenario_id` A–D, bounded query, clearance and `mock|live` mode); invokes the existing LangGraph/R2/R3 workflow and persists a run. Live Groq still proposes plans only. |
| `GET /api/v1/analysis-runs?offset=&limit=` | Offset-paginated run list; `limit` is bounded to 100. |
| `GET /api/v1/analysis-runs/{run_id}` | Run lifecycle, redacted request metadata and sanitized R4/R3 result. |
| `GET /api/v1/analysis-runs/{run_id}/findings` | Paginated relational R3 findings. |
| `GET /api/v1/analysis-runs/{run_id}/evidence/references` | Paginated relational evidence references/digests. |
| `GET /api/v1/analysis-runs/{run_id}/events` | Paginated MongoDB observed events with execution/invocation/tool provenance. |
| `GET /api/v1/analysis-runs/{run_id}/evidence` | Paginated sanitized MongoDB evidence documents. |
| `POST /api/v1/analysis-runs/{run_id}/reconcile` | Idempotently retries a `PERSISTENCE_PENDING` Mongo write using the staged SQL snapshot. |
| `POST /api/v1/policies/index` | Accepts `{ "relative_path": "..." }`; the source must resolve under `CHAIN_SCOPE_POLICY_DIR`, be Markdown/TXT, parse as an ACTIVE policy, and be indexed via local Chroma. PostgreSQL policy metadata is upserted after Chroma ingestion. |
| `POST /api/v1/policies/{document_id}/deactivate` | Marks indexed chunks OBSOLETE rather than deleting source provenance; updates policy metadata. |
| `GET /api/v1/policies/search?q=&clearance=&top_k=` | Retrieves up to 10 passages under Chroma's active-status and clearance filters. Retrieved text is returned only to the local caller and is not retained in R5's persisted run report. |

Requests use Pydantic validation, reject extra fields where a request model applies, bound pagination/top-k, and return safe error summaries. Raw query text is never stored: PostgreSQL retains only its SHA-256 digest and character count. Persisted result citations omit retrieved text excerpts. MongoDB event/evidence writes use stable per-run identities and idempotent upserts. PostgreSQL retains a temporary retry snapshot during a cross-database partial failure; the system does not claim a distributed transaction.

Policy indexing/deactivation spans Chroma and PostgreSQL and is not atomic. If metadata persistence fails after the Chroma operation, inspect both stores and re-run the idempotent indexing operation or restore the policy metadata manually before treating the operation as complete.

## Security boundary and not-yet-implemented contracts

Local-only mode is enforced by development/test environment and loopback bind configuration. R5 does not implement authentication, authorization, tenant ownership, CSRF/session handling, quotas, rate limiting, production telemetry or a public deployment. To make endpoints available, set `APP_ENV=development` and `HOST=127.0.0.1`; configure `CHAIN_SCOPE_POSTGRES_DSN`, `CHAIN_SCOPE_MONGODB_URI`, and optionally `CHAIN_SCOPE_MONGODB_DATABASE`. Never put credentials in Git or `.env.example`.

All R1 contracts for tools/catalog CRUD, user/role access, campaigns, scenario administration, remediation/verification, and the dashboard remain logical only. R5 does not start R6 or authorize a UI/dashboard, multi-user access, deployment, real external tools, or tablet validation.
