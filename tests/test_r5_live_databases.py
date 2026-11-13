"""Opt-in integration tests against explicitly dedicated PostgreSQL/Mongo test databases.

Before running: apply `alembic upgrade head` to the dedicated PostgreSQL test DB,
then set CHAIN_SCOPE_TEST_POSTGRES_DSN, CHAIN_SCOPE_TEST_MONGODB_URI, and
CHAIN_SCOPE_TEST_MONGODB_DATABASE. The test refuses databases not named as test DBs.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from urllib.parse import urlparse

import pytest
from sqlalchemy import delete

from app.database.models import AnalysisRunRecord
from app.database.mongo import MongoDocumentStore
from app.database.postgres import PostgresRepository


PG_DSN = os.getenv("CHAIN_SCOPE_TEST_POSTGRES_DSN", "")
MONGO_URI = os.getenv("CHAIN_SCOPE_TEST_MONGODB_URI", "")
MONGO_DB = os.getenv("CHAIN_SCOPE_TEST_MONGODB_DATABASE", "")
LIVE_SERVICES_CONFIGURED = bool(PG_DSN and MONGO_URI and MONGO_DB)


@pytest.mark.skipif(not LIVE_SERVICES_CONFIGURED,
                    reason="Dedicated PostgreSQL and Mongo integration test databases are not configured")
def test_real_postgres_and_mongo_persistence_round_trip():
    postgres_name = urlparse(PG_DSN).path.strip("/").lower()
    if "test" not in postgres_name or "test" not in MONGO_DB.lower():
        pytest.fail("Live R5 integration tests require explicitly named *_test databases")

    async def scenario():
        repo = PostgresRepository(PG_DSN)
        mongo = MongoDocumentStore(MONGO_URI, MONGO_DB)
        run_id = "it-" + uuid.uuid4().hex
        evidence_id = "evidence:" + uuid.uuid4().hex
        finding_id = "finding:" + uuid.uuid4().hex
        event_id = "event:" + uuid.uuid4().hex
        try:
            await repo.check_health()
            await mongo.check_health()
            await repo.create_run(run_id=run_id, request_payload={"scenario_id": "C"},
                                  scenario_id="C", planner_mode="mock")
            evidence = [{"evidence_id": evidence_id, "kind": "integration_test",
                         "sha256": "b" * 64, "recorded_at": "2026-11-14T00:00:00+00:00",
                         "classification": "INTERNAL"}]
            finding = [{"finding_id": finding_id, "execution_id": "execution:" + uuid.uuid4().hex,
                        "finding_type": "INTEGRATION_TEST", "assessment": "INCONCLUSIVE",
                        "severity": "LOW", "classification": "INTERNAL", "status": "OPEN",
                        "summary": "synthetic test row", "evidence_ids": [evidence_id],
                        "payload": {"test": True}}]
            execution_id = finding[0]["execution_id"]
            result = {"test": "R5 database round-trip"}
            retry_payload = {"events": [], "evidence_documents": []}
            await repo.stage_result(run_id, execution_id=execution_id, workflow_status="COMPLETED",
                                    planner_mode="mock", result_payload=result,
                                    retry_payload=retry_payload, error_codes=[])
            await mongo.persist_run_documents(run_id, events=[{
                "event_id": event_id, "execution_id": execution_id, "invocation_id": "invocation:test",
                "tool_id": "synthetic-tool", "sequence": 1, "classification": "INTERNAL",
            }], evidence_documents=[{
                "evidence_id": evidence_id, "kind": "integration_test", "sha256": "b" * 64,
                "recorded_at": "2026-11-14T00:00:00+00:00", "classification": "INTERNAL",
                "payload": {"event_id": event_id},
            }])
            await repo.finalize_run(run_id, status="COMPLETED", workflow_status="COMPLETED",
                                    result_payload=result, execution_id=execution_id,
                                    findings=finding, evidence_references=evidence)
            row = await repo.get_run(run_id)
            finding_rows = await repo.get_findings(run_id, offset=0, limit=10)
            event_rows = await mongo.get_events(run_id, offset=0, limit=10)
            evidence_rows = await mongo.get_evidence_documents(run_id, offset=0, limit=10)
            assert row and row["status"] == "COMPLETED"
            assert finding_rows["total"] == 1
            assert event_rows["total"] == 1 and event_rows["items"][0]["event_id"] == event_id
            assert evidence_rows["total"] == 1 and evidence_rows["items"][0]["evidence_id"] == evidence_id
        finally:
            async with repo.sessions.begin() as session:
                await session.execute(delete(AnalysisRunRecord).where(AnalysisRunRecord.run_id == run_id))
            await mongo.events.delete_many({"run_id": run_id})
            await mongo.evidence.delete_many({"run_id": run_id})
            await mongo.close()
            await repo.close()

    asyncio.run(scenario())
