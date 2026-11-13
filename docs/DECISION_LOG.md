# Decision Log

## D-001 — Remote-first isolated project (2026-11-13)
Create a separate `chainscope-x` workspace because the Samsung tablet is unavailable. Never claim access to or modify tablet files. Approved in the supplied charter.

## D-002 — Minimal FastAPI foundation using existing dependencies (2026-11-13)
Use installed FastAPI/Jinja2/Uvicorn and standard-library `unittest`; do not install packages. Pytest and HTTPX were absent in R0.

## D-003 — SQL/NoSQL academic requirement unresolved
PostgreSQL + JSONB and ChromaDB are the proposed design; this is not asserted to satisfy a rubric demanding an independent document-oriented NoSQL database. Verify the exact rubric. Seek Project Director approval before adding another database. Open.

## D-004 — Tablet compatibility is pending
R0/R1 ran on Linux ARM64 with Python 3.12.3, not the tablet. Compatibility remains pending tablet phase T1.

## D-005 — R1 accepted; R2 separately authorized (2026-11-13)
The R2 manager directive accepts R0 and R1 and explicitly authorizes R2 only. R3 and later are not authorized. The final R1 commit and recovery ZIP/bundle checksums were verified before R2 changes. Preserve accepted history and archives.

## D-006 — Pydantic v2 contracts as R1 executable contract source
Use the installed Pydantic with FastAPI for small deterministic model validation and generated JSON Schema snapshots. No new dependency was installed. Schemas are design/validation artifacts, not database constraints or end-to-end service behavior.

## D-007 — Event provenance and bounded coverage are first-class
Every observed effect requires execution/invocation/tool identity and evidence reference. Incomplete coverage cannot prove absence of a violation. COMPLETE applies only to an explicit tested instrumentation scope. LLM-generated explanations are not authoritative evidence.

## D-008 — Classification and policy constraints
Transformations inherit the highest sensitivity input. Downgrades/declassification are not supported without a separate explicit tested rule. Confirmed violations require an applicable active policy plus event-backed path/evidence. Negative conclusions require COMPLETE coverage of the stated scope.

## D-009 — Manager handoff as the single user-facing report
Create one consolidated `MANAGER_HANDOFF_R1.txt` for R1 and one `MANAGER_HANDOFF_R2.txt` for R2. Technical documentation remains in the repository. New recovery artifacts use R2-specific filenames; R0/R1 archives are not overwritten.

## D-010 — Missing pre-existing documents
At R1 start, `docs/PROJECT_CHARTER.md` and `docs/ARCHITECTURE.md` were absent. The architecture document was created as an R1 deliverable. The supplied master prompt and manager directives govern; no unverified charter content is inferred.

## D-011 — Reuse R1 effect and coverage semantics without contract extension (R2)
All observed effects use the existing R1 `EffectType` values (`READS`, `SEARCHES`, `TRANSFORMS`, `CREATES`, `WRITES`, `TRANSMITS`) and `ObservedEffect`/`CoverageRecord` fields. R2 examples such as “READ” and “SEARCH” map to the R1 enum values `READS` and `SEARCHES`; no new enum, field, schema snapshot, or breaking change was introduced.

## D-012 — Trusted static implementations and shared local adapters (R2)
Register only the six exact approved Python implementation classes. The tools have no dynamic loader, subprocess, shell, socket, or unrestricted filesystem path. Resource adapters—not tool-authored assertions—perform operations and invoke the shared recorder. The external destination is an in-memory abstraction only.

## D-013 — Evidence and coverage remain explicitly bounded (R2)
Store only sanitized structured event facts locally and resolve each evidence reference against a real in-memory evidence record. Event metadata excludes file contents, queries, free-form names, and untrusted resource/tool identifiers; unresolved inputs use stable placeholders. SHA-256 over canonical sanitized facts is an integrity check for test records, not proof of execution. COMPLETE describes only an explicit tested adapter scope; it does not imply OS-wide monitoring.

## D-014 — Adversarial storage copy is an opt-in fixture, not a verdict (R2)
A narrow execution fixture adds a second in-memory copy from Workspace Storage to the simulated external sink and records it as `TRANSMITS`. The declared R1 manifest remains unchanged. R2 records the operation only; mismatch explanation and maliciousness analysis are deferred.

## D-015 — R2 is process-local and non-persistent
R2 execution, fixture, workspace, destination, and evidence data are in memory. No database package, PostgreSQL/Supabase connection, migrations, or external service is introduced. Later persistence must preserve these adapter boundaries and R1 contracts.
