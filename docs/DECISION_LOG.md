# Decision Log

## D-001 — Remote-first isolated project (2026-11-13)
Create a separate `chainscope-x` workspace because the Samsung tablet is unavailable. Never claim access to or modify tablet files. Approved in the supplied charter.

## D-002 — Minimal FastAPI foundation using existing dependencies (2026-11-13)
Use installed FastAPI/Jinja2/Uvicorn and standard-library `unittest`; do not install packages. Pytest and HTTPX were absent in R0.

## D-003 — SQL/NoSQL academic requirement unresolved
PostgreSQL + JSONB and ChromaDB are the proposed design; this is not asserted to satisfy a rubric demanding an independent document-oriented NoSQL database. Verify the exact rubric. Seek Project Director approval before adding another database. Open.

## D-004 — Tablet compatibility is pending
R0/R1 ran on Linux ARM64 with Python 3.12.3, not the tablet. Compatibility remains pending tablet phase T1.

## D-005 — R1 accepted and authorized (2026-11-13)
Manager directive states R0 accepted administratively and explicitly approves R1 only. R2 is not approved. R0 commit and recovery artifacts were verified before changes; no R0 source or history was rewritten.

## D-006 — Pydantic v2 contracts as R1 executable contract source
Use the Pydantic already installed with FastAPI for small deterministic model validation and generated JSON Schema snapshots. No new dependency was installed. Schemas are design/validation artifacts, not an implementation of database constraints or end-to-end service behavior.

## D-007 — Event provenance and bounded coverage are first-class
Every observed effect requires execution/invocation/tool identity and evidence reference. Incomplete coverage cannot prove absence of a violation. COMPLETE applies only to an explicit tested instrumentation scope. LLM-generated explanations are not authoritative evidence.

## D-008 — Classification and policy constraints
Transformations inherit the highest sensitivity input. Downgrades/declassification are not supported without a separate explicit tested rule. Confirmed violations require an applicable active policy plus event-backed path/evidence. An observed positive violation may still be established under partial overall coverage; negative conclusions require COMPLETE coverage of stated scope.

## D-009 — Manager handoff as the single user-facing report
Create one `MANAGER_HANDOFF_R1.txt` consolidated report as requested. Technical documentation remains in the repository; R0 archive names are preserved and not overwritten.

## D-010 — Missing pre-existing documents
At R1 start, `docs/PROJECT_CHARTER.md` and `docs/ARCHITECTURE.md` were absent. The architecture document is created as an R1 deliverable. The supplied master prompt and manager directive govern; no unverified charter content is inferred.
