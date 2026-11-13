# Decision Log

## D-001 — Remote-first isolated project (2026-11-13)
- **Decision:** Create a separate `chainscope-x` workspace in the available sandbox.
- **Reason:** The Samsung tablet and its files are unavailable; never modify or claim inspection of them.
- **Alternatives:** Wait for tablet access (rejected for R0); attempt to access tablet files (not possible and prohibited).
- **Status:** Approved by the supplied project charter for R0.

## D-002 — Minimal FastAPI foundation using existing dependencies (2026-11-13)
- **Decision:** Use installed FastAPI/Jinja2/Uvicorn and standard-library `unittest`; do not install packages.
- **Reason:** These imports are already available. Pytest and HTTPX are absent; tests avoid depending on them.
- **Status:** R0 implementation choice only.

## D-003 — SQL/NoSQL academic requirement unresolved
- **Decision:** PostgreSQL + JSONB and ChromaDB are the currently proposed design; this is not asserted to satisfy a separate document-oriented NoSQL requirement.
- **Required follow-up:** Verify the exact instructor rubric. Ask Project Director before adding another database if explicitly required.
- **Status:** Open.

## D-004 — Tablet compatibility is pending
- **Decision:** No compatibility claim based on this ARM64 sandbox; Python here is 3.12.3, not the historical tablet version.
- **Status:** Open until tablet phase T1.
