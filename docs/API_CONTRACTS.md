# API Contracts (R1 logical design)

These are future FastAPI JSON endpoints, not implemented routes. Except public liveness, every endpoint requires a verified server-side identity and role/ownership authorization. Fail closed when production authentication is absent. Validate request and response schemas, use JSON, UTC ISO-8601 timestamps, pagination, stable IDs, and safe non-secret errors.

Common error envelope: `{"error":{"code":"VALIDATION_ERROR|NOT_FOUND|FORBIDDEN|CONFLICT|INCONCLUSIVE|INTERNAL_ERROR","message":"safe summary","request_id":"..."}}`. Do not expose stack traces, credentials, private payloads, or existence of another tenant's resources. Use 400/422 for malformed input, 401 unauthenticated, 403 forbidden, 404 missing, 409 state conflict, 429 throttling, and 500 safe internal failure.

## Resource contracts

| Group / routes | Request structure | Response structure | Minimum role |
|---|---|---|---|
| Tools: `GET/POST /api/tools`, `GET /api/tools/{id}` | Create body is `ToolManifest`; list accepts `status`, `capability`, `page`, `page_size`. | Create/detail returns `{tool_id, version, manifest, created_at}`; list returns `{items:[...], next_cursor}`. | Viewer read; analyst create; admin manage |
| Policies: `GET/POST /api/policies`, `POST /api/policies/{id}/versions` | Draft body `{policy_id, version, source, effective_from, rule: PolicyRule, access_classification}`; upload uses separate private-file flow. | `{policy_id, versions:[{version,status,effective_from,source_ref}]}`; activation recorded as audited state change. | Viewer read; analyst draft; admin activate |
| Scenarios: `GET/POST /api/scenarios` | Create `{scenario_id, description, fixture_refs, expected_label, expected_effects}`; fixture references only, never arbitrary executable code. | `{scenario_id, status, version, created_at}`; list uses `{items,next_cursor}`. | Viewer read; analyst create |
| Campaigns: `POST /api/campaigns`, `GET /api/campaigns/{id}` | Create `{name, scenario_ids, tool_ids, bounded_config}`. | `{campaign_id,status,execution_ids,created_at}`; detail includes per-run outcomes. | Analyst create/run; viewer read |
| Executions: `POST /api/executions`, `GET /api/executions/{id}` | Start `{scenario_id, tool_ids, policy_version_ids, mock_mode}`; campaign start references `campaign_id`. | `{execution_id,status,started_at,coverage:{coverage_id,status,scope,gaps},result_ref}`. Coverage does not default to COMPLETE. | Analyst run; viewer read |
| Effects: `GET /api/executions/{id}/effects` | Query by cursor, tool, effect type, sequence. No client-created effect is accepted as recorder truth. | `{items:[ObservedEffect],next_cursor,coverage_status}` with event/invocation/execution provenance. | Viewer read |
| Findings: `GET /api/findings`, `GET /api/findings/{id}` | List filters severity, assessment, status, execution, cursor. | `{items:[FindingSummary],next_cursor}`; detail `{finding,policy_version,path,evidence_refs,coverage,uncertainty}`. | Viewer read; analyst annotate |
| Graph: `GET /api/executions/{id}/graph` | Query filters node types, destination, max path depth (bounded). | `{execution_id,nodes:[GraphNode],edges:[GraphEdge],paths:[CapabilityPath],coverage}`. Client cannot create authoritative edges. | Viewer read |
| Remediation: `POST /api/findings/{id}/remediations`, `GET /api/remediations/{id}` | Create body `RemediationCandidate` without VERIFIED status, including benign workflows and criteria. | `{remediation_id,status:"PROPOSED",target,blocked_path,verification_criteria}`. Any test application is restricted to isolated approved profile. | Analyst propose; admin approve/apply |
| Verification: `POST /api/remediations/{id}/verification-runs` | `{scenario_ids, required_outcomes, bounded_config}`; only approved synthetic scenarios. | `{verification_run_id,status,outcomes,evidence_ids,execution_ids,completed_at}`. VERIFIED only after criteria and evidence pass. | Analyst run; admin approve |
| Dashboard: `GET /api/dashboard/summary` | Query time window and optional scope. | `{as_of,scope,coverage_denominator,tool_count,campaign_count,observed_effect_count,mismatch_count,findings_by_severity,recent_runs}`; unknown metric is null/unknown, not fabricated zero. | Viewer read |

## Shared behavior
All list responses are paginated; request IDs are returned for traceability. Every response is filtered by tenant/ownership and role. State transitions use optimistic concurrency or explicit 409 conflicts. Event/finding evidence references are access-controlled and do not expose sensitive document contents by default. HTMX forms/pages call the same service layer and enforce CSRF/session/auth policies.

Endpoint names and wire examples are logical contracts; review during API implementation before freezing a public version. No routes beyond R0 liveness/page, authentication, pagination, CRUD, or business behavior are claimed implemented in R1.
