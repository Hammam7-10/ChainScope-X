
## 2026-11-14 — R5
- Added an async SQLAlchemy/asyncpg PostgreSQL repository, Alembic migration, MongoDB Async event/evidence document store, and idempotent cross-store reconciliation snapshots.
- Added a bounded local-only `/api/v1` for analysis runs, findings/evidence/events, dependency health, reconciliation, and controlled policy index/deactivate/search operations.
- Kept R3 as the only security verdict authority; redacted persisted queries and retrieved policy excerpts; added pending policy lifecycle guards and OBSOLETE filtering.
- Added SQLite-backed SQL repository tests, Mongo-adapter test doubles, real R4 mock workflow persistence tests, policy-operation tests, and an opt-in live PostgreSQL/Mongo integration test.
- Added R5 database/API specifications, local setup guide, phase report and manager handoff. See `docs/PHASE_REPORTS/R5.md` and `MANAGER_HANDOFF_R5.txt`.
