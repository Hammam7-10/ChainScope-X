"""PyMongo Async adapter for structured execution-event and evidence documents."""
from __future__ import annotations

from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient


class MongoDocumentStore:
    def __init__(self, uri: str, database: str, *, client: AsyncMongoClient | None = None) -> None:
        self.client = client or AsyncMongoClient(
            uri, serverSelectionTimeoutMS=2_500, connectTimeoutMS=2_500,
            retryWrites=True, appname="ChainScope-X-R5",
        )
        self.database = self.client[database]
        self.events = self.database["execution_events"]
        self.evidence = self.database["evidence_documents"]

    async def close(self) -> None:
        await self.client.close()

    async def check_health(self) -> None:
        await self.client.admin.command("ping")

    async def ensure_indexes(self) -> None:
        await self.events.create_index([("run_id", ASCENDING), ("event.sequence", ASCENDING)])
        await self.events.create_index([("execution_id", ASCENDING), ("event.event_id", ASCENDING)])
        await self.evidence.create_index([("run_id", ASCENDING), ("evidence_id", ASCENDING)], unique=True)
        await self.evidence.create_index([("sha256", ASCENDING)])
        await self.evidence.create_index([("classification", ASCENDING)])

    async def persist_run_documents(self, run_id: str, *,
                                    events: Iterable[dict[str, Any]],
                                    evidence_documents: Iterable[dict[str, Any]]) -> None:
        await self.ensure_indexes()
        for item in events:
            event_id = str(item["event_id"])
            document = {
                "_id": f"{run_id}:{event_id}", "run_id": run_id,
                "execution_id": item.get("execution_id"), "event_id": event_id,
                "classification": item.get("classification"),
                "provenance": {"execution_id": item.get("execution_id"),
                               "invocation_id": item.get("invocation_id"),
                               "tool_id": item.get("tool_id"), "sequence": item.get("sequence")},
                "event": item,
            }
            await self.events.replace_one({"_id": document["_id"]}, document, upsert=True)
        for item in evidence_documents:
            evidence_id = str(item["evidence_id"])
            document = {"_id": f"{run_id}:{evidence_id}", "run_id": run_id,
                        "evidence_id": evidence_id, **item}
            await self.evidence.replace_one({"_id": document["_id"]}, document, upsert=True)

    async def get_events(self, run_id: str, *, offset: int, limit: int) -> dict[str, Any]:
        query = {"run_id": run_id}
        total = await self.events.count_documents(query)
        cursor = self.events.find(query, {"_id": 0}).sort(
            [("event.sequence", ASCENDING), ("event_id", ASCENDING)]).skip(offset).limit(limit)
        items = await cursor.to_list(length=limit)
        return {"items": items, "offset": offset, "limit": limit, "total": total,
                "next_offset": offset + len(items) if offset + len(items) < total else None}

    async def get_evidence_documents(self, run_id: str, *, offset: int, limit: int) -> dict[str, Any]:
        query = {"run_id": run_id}
        total = await self.evidence.count_documents(query)
        cursor = self.evidence.find(query, {"_id": 0}).sort("evidence_id", ASCENDING).skip(offset).limit(limit)
        items = await cursor.to_list(length=limit)
        return {"items": items, "offset": offset, "limit": limit, "total": total,
                "next_offset": offset + len(items) if offset + len(items) < total else None}
