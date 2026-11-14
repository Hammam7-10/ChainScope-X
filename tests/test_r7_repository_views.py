from __future__ import annotations
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.database.models import Base
from app.database.postgres import PostgresRepository


def test_run_filters_and_dashboard_summary_use_persisted_rows():
    async def exercise():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        repo = PostgresRepository("sqlite+aiosqlite:///:memory:", engine=engine)
        await repo.create_run(run_id="run-a", request_payload={"scenario_id": "A"}, scenario_id="A", planner_mode="mock")
        await repo.create_run(run_id="run-b", request_payload={"scenario_id": "B"}, scenario_id="B", planner_mode="mock")
        page = await repo.list_runs(offset=0, limit=1, scenario_id="A")
        assert page["total"] == 1
        assert [row["run_id"] for row in page["items"]] == ["run-a"]
        summary = await repo.dashboard_summary()
        assert summary["run_total"] == 2
        assert summary["finding_total"] == 0
        assert summary["recent_findings"] == []
        await engine.dispose()
    asyncio.run(exercise())
