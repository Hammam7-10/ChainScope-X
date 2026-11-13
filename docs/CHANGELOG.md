# Changelog

## 2026-11-13 — R0
- Created isolated ChainScope X portable starter foundation.
- Added minimal FastAPI app, health endpoint, responsive local page, and standard-library tests.
- Added project governance, environment, recovery, and phase documentation.
- Initialized Git and generated R0 source/history/checksum exports.

## 2026-11-13 — R4
- Added persistent local ChromaDB retrieval with FastEmbed/ONNX bilingual embeddings, source/version/access metadata, and Arabic/English retrieval tests.
- Added one compiled LangGraph workflow, deterministic mock planning, optional Groq plan proposal, strict plan validation, and structured JSON CLI reports.
- Connected bounded plans to the synthetic R2 runner and deterministic R3 analysis service; completed scenarios A–D without granting the planner verdict authority.
- Added RAG/agent specs, restore instructions, full phase report, R4 dependency/test setup, and test evidence. See `docs/PHASE_REPORTS/R4.md`.

## 2026-11-14 — R5
- Added an async SQLAlchemy/asyncpg PostgreSQL repository, Alembic migration, MongoDB Async event/evidence document store, and idempotent cross-store reconciliation snapshots.
- Added a bounded local-only `/api/v1` for analysis runs, findings/evidence/events, dependency health, reconciliation, and controlled policy index/deactivate/search operations.
- Kept R3 as the only security verdict authority; redacted persisted queries and retrieved policy excerpts; added pending policy lifecycle guards and OBSOLETE filtering.
- Added SQLite-backed SQL repository tests, Mongo-adapter test doubles, real R4 mock workflow persistence tests, policy-operation tests, and an opt-in live PostgreSQL/Mongo integration test.
- Added an optional local PostgreSQL/Mongo Compose configuration (loopback-bound, no committed passwords), R5 database/API specifications, local setup guide, phase report and manager handoff. See `docs/PHASE_REPORTS/R5.md` and `MANAGER_HANDOFF_R5.txt`.
