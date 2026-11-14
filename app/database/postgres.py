"""PostgreSQL repository for durable run, finding, evidence-reference and policy metadata."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import (
    AnalysisRunRecord, EvidenceReferenceRecord, FindingEvidenceLink, FindingRecord,
    PolicyDocumentRecord, UserRecord,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresRepository:
    def __init__(self, dsn: str, *, engine: AsyncEngine | None = None) -> None:
        self.engine = engine or create_async_engine(dsn, pool_pre_ping=True, pool_size=5, max_overflow=5)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()

    async def check_health(self) -> None:
        async with self.sessions() as session:
            await session.execute(text("SELECT 1"))

    async def get_or_create_user(self, *, google_subject: str, email: str,
                                 display_name: str, admin_subjects: set[str] | frozenset[str]) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            row = await session.scalar(select(UserRecord).where(UserRecord.google_subject == google_subject))
            now = utcnow()
            if row is None:
                row = UserRecord(
                    user_id="user-" + hashlib.sha256(google_subject.encode("utf-8")).hexdigest()[:55], google_subject=google_subject,
                    email=email, display_name=display_name or email, role=("admin" if google_subject in admin_subjects else "viewer"),
                    active=True, created_at=now, updated_at=now, last_login_at=now,
                )
                session.add(row)
            else:
                row.email = email
                row.display_name = display_name or email
                row.updated_at = now
                row.last_login_at = now
            await session.flush()
            return self._user_dict(row)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = await session.get(UserRecord, user_id)
            if row is None or not row.active:
                return None
            return self._user_dict(row)

    async def create_run(self, *, run_id: str, request_payload: dict[str, Any],
                         scenario_id: str, planner_mode: str) -> None:
        async with self.sessions.begin() as session:
            session.add(AnalysisRunRecord(
                run_id=run_id, execution_id=None, scenario_id=scenario_id,
                status="RUNNING", workflow_status="RUNNING", planner_mode=planner_mode,
                request_payload=request_payload, error_codes=[], started_at=utcnow(),
            ))

    async def stage_result(self, run_id: str, *, execution_id: str | None,
                           workflow_status: str, planner_mode: str | None,
                           result_payload: dict[str, Any], retry_payload: dict[str, Any],
                           error_codes: list[str]) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AnalysisRunRecord, run_id)
            if row is None:
                raise KeyError("Analysis run not found")
            row.execution_id = execution_id
            row.status = "PERSISTENCE_PENDING"
            row.workflow_status = workflow_status
            row.planner_mode = planner_mode
            row.result_payload = result_payload
            row.retry_payload = retry_payload
            row.error_codes = error_codes

    async def finalize_run(self, run_id: str, *, status: str,
                           result_payload: dict[str, Any], workflow_status: str,
                           execution_id: str | None, findings: Sequence[dict[str, Any]],
                           evidence_references: Sequence[dict[str, Any]],
                           error_codes: list[str] | None = None) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AnalysisRunRecord, run_id)
            if row is None:
                raise KeyError("Analysis run not found")
            finding_ids = select(FindingRecord.finding_id).where(FindingRecord.run_id == run_id)
            await session.execute(delete(FindingEvidenceLink).where(FindingEvidenceLink.finding_id.in_(finding_ids)))
            await session.execute(delete(FindingRecord).where(FindingRecord.run_id == run_id))
            await session.execute(delete(EvidenceReferenceRecord).where(EvidenceReferenceRecord.run_id == run_id))
            row.execution_id = execution_id
            row.status = status
            row.workflow_status = workflow_status
            row.result_payload = result_payload
            row.retry_payload = None
            row.error_codes = list(error_codes or [])
            row.completed_at = utcnow()
            for value in evidence_references:
                ref_time = value.get("recorded_at")
                if isinstance(ref_time, str):
                    ref_time = datetime.fromisoformat(ref_time.replace("Z", "+00:00"))
                if ref_time is None:
                    ref_time = utcnow()
                session.add(EvidenceReferenceRecord(
                    run_id=run_id, evidence_id=value["evidence_id"], kind=value["kind"],
                    sha256=value.get("sha256"), recorded_at=ref_time,
                    source_document_id=value.get("source_document_id"),
                    classification=value.get("classification"),
                ))
            for value in findings:
                session.add(FindingRecord(
                    finding_id=value["finding_id"], run_id=run_id,
                    execution_id=value["execution_id"], finding_type=value["finding_type"],
                    assessment=value["assessment"], severity=value["severity"],
                    classification=value.get("classification"), status=value["status"],
                    summary=value.get("summary", ""), payload=value["payload"],
                ))
            for value in findings:
                for evidence_id in set(value.get("evidence_ids", [])):
                    if evidence_id in {item["evidence_id"] for item in evidence_references}:
                        session.add(FindingEvidenceLink(
                            finding_id=value["finding_id"], run_id=run_id, evidence_id=evidence_id,
                        ))

    async def mark_failed(self, run_id: str, *, error_code: str) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AnalysisRunRecord, run_id)
            if row is not None:
                row.status = "FAILED"
                row.workflow_status = "FAILED"
                row.error_codes = list(dict.fromkeys([*(row.error_codes or []), error_code]))
                row.completed_at = utcnow()

    async def get_retry_payload(self, run_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = await session.get(AnalysisRunRecord, run_id)
            if row is None:
                raise KeyError("Analysis run not found")
            return row.retry_payload

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = await session.get(AnalysisRunRecord, run_id)
            return self._run_dict(row) if row else None

    async def list_runs(self, *, offset: int, limit: int, scenario_id: str | None = None,
                        status: str | None = None) -> dict[str, Any]:
        async with self.sessions() as session:
            stmt = select(AnalysisRunRecord)
            count_stmt = select(func.count()).select_from(AnalysisRunRecord)
            if scenario_id:
                stmt, count_stmt = stmt.where(AnalysisRunRecord.scenario_id == scenario_id), count_stmt.where(AnalysisRunRecord.scenario_id == scenario_id)
            if status:
                stmt, count_stmt = stmt.where(AnalysisRunRecord.status == status), count_stmt.where(AnalysisRunRecord.status == status)
            total = int((await session.scalar(count_stmt)) or 0)
            rows = (await session.scalars(stmt.order_by(
                AnalysisRunRecord.started_at.desc(), AnalysisRunRecord.run_id.desc()
            ).offset(offset).limit(limit))).all()
            return {"items": [self._run_dict(row) for row in rows], "offset": offset,
                    "limit": limit, "total": total, "next_offset": offset + len(rows) if offset + len(rows) < total else None}

    async def get_findings(self, run_id: str, *, offset: int, limit: int) -> dict[str, Any] | None:
        async with self.sessions() as session:
            if await session.get(AnalysisRunRecord, run_id) is None:
                return None
            total = int((await session.scalar(select(func.count()).select_from(FindingRecord).where(
                FindingRecord.run_id == run_id))) or 0)
            rows = (await session.scalars(select(FindingRecord).where(
                FindingRecord.run_id == run_id).order_by(FindingRecord.severity, FindingRecord.finding_id)
                .offset(offset).limit(limit))).all()
            return {"items": [self._finding_dict(row) for row in rows], "offset": offset,
                    "limit": limit, "total": total, "next_offset": offset + len(rows) if offset + len(rows) < total else None}

    async def get_evidence_references(self, run_id: str, *, offset: int, limit: int) -> dict[str, Any] | None:
        async with self.sessions() as session:
            if await session.get(AnalysisRunRecord, run_id) is None:
                return None
            total = int((await session.scalar(select(func.count()).select_from(EvidenceReferenceRecord).where(
                EvidenceReferenceRecord.run_id == run_id))) or 0)
            rows = (await session.scalars(select(EvidenceReferenceRecord).where(
                EvidenceReferenceRecord.run_id == run_id).order_by(EvidenceReferenceRecord.recorded_at,
                EvidenceReferenceRecord.evidence_id).offset(offset).limit(limit))).all()
            return {"items": [self._evidence_dict(row) for row in rows], "offset": offset,
                    "limit": limit, "total": total, "next_offset": offset + len(rows) if offset + len(rows) < total else None}

    async def upsert_policy_metadata(self, metadata: dict[str, Any]) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(PolicyDocumentRecord, metadata["document_id"])
            if row is None:
                row = PolicyDocumentRecord(document_id=metadata["document_id"], version=metadata["version"],
                    status=metadata["document_status"], access_classification=metadata["access_classification"],
                    source=metadata["source"], content_sha256=metadata["content_sha256"],
                    metadata_payload=metadata, updated_at=utcnow())
                session.add(row)
            else:
                row.version = metadata["version"]
                row.status = metadata["document_status"]
                row.access_classification = metadata["access_classification"]
                row.source = metadata["source"]
                row.content_sha256 = metadata["content_sha256"]
                row.metadata_payload = metadata
                row.updated_at = utcnow()

    async def get_policy_metadata(self, document_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = await session.get(PolicyDocumentRecord, document_id)
            if row is None:
                return None
            return {"document_id": row.document_id, "version": row.version,
                    "document_status": row.status, "access_classification": row.access_classification,
                    "source": row.source, "content_sha256": row.content_sha256,
                    "metadata": row.metadata_payload}

    async def get_inactive_policy_document_ids(self) -> set[str]:
        async with self.sessions() as session:
            rows = await session.scalars(select(PolicyDocumentRecord.document_id).where(
                PolicyDocumentRecord.status == "OBSOLETE"))
            return set(rows.all())

    async def get_pending_policy_document_ids(self) -> set[str]:
        async with self.sessions() as session:
            rows = await session.scalars(select(PolicyDocumentRecord.document_id).where(
                PolicyDocumentRecord.status.in_(["INDEXING_PENDING", "DEACTIVATION_PENDING"])))
            return set(rows.all())

    async def dashboard_summary(self) -> dict[str, Any]:
        async with self.sessions() as session:
            run_total = int((await session.scalar(select(func.count()).select_from(AnalysisRunRecord))) or 0)
            finding_total = int((await session.scalar(select(func.count()).select_from(FindingRecord))) or 0)
            pending = int((await session.scalar(select(func.count()).select_from(AnalysisRunRecord).where(
                AnalysisRunRecord.status == "PERSISTENCE_PENDING"))) or 0)
            rows = (await session.scalars(select(AnalysisRunRecord).order_by(
                AnalysisRunRecord.started_at.desc(), AnalysisRunRecord.run_id.desc()).limit(8))).all()
            latest_findings = (await session.scalars(select(FindingRecord).join(
                AnalysisRunRecord, FindingRecord.run_id == AnalysisRunRecord.run_id).order_by(
                AnalysisRunRecord.completed_at.desc().nullslast(), AnalysisRunRecord.started_at.desc(),
                FindingRecord.finding_id.desc()).limit(6))).all()
            assessments = (await session.execute(select(FindingRecord.assessment, func.count()).group_by(
                FindingRecord.assessment))).all()
            severities = (await session.execute(select(FindingRecord.severity, func.count()).group_by(
                FindingRecord.severity))).all()
            return {"run_total": run_total, "finding_total": finding_total,
                    "persistence_pending": pending, "recent_runs": [self._run_dict(row) for row in rows],
                    "recent_findings": [self._finding_dict(row) for row in latest_findings],
                    "finding_assessments": {str(k): int(v) for k, v in assessments},
                    "finding_severities": {str(k): int(v) for k, v in severities},
                    "coverage": "Coverage is reported per run; no aggregate coverage metric is stored."}

    async def list_findings(self, *, offset: int, limit: int, severity: str | None = None,
                            assessment: str | None = None, query: str | None = None) -> dict[str, Any]:
        async with self.sessions() as session:
            stmt = select(FindingRecord)
            count_stmt = select(func.count()).select_from(FindingRecord)
            if severity:
                stmt = stmt.where(FindingRecord.severity == severity)
                count_stmt = count_stmt.where(FindingRecord.severity == severity)
            if assessment:
                stmt = stmt.where(FindingRecord.assessment == assessment)
                count_stmt = count_stmt.where(FindingRecord.assessment == assessment)
            if query:
                pattern = f"%{query}%"
                stmt = stmt.where((FindingRecord.finding_id.ilike(pattern)) | (FindingRecord.summary.ilike(pattern)) | (FindingRecord.finding_type.ilike(pattern)))
                count_stmt = count_stmt.where((FindingRecord.finding_id.ilike(pattern)) | (FindingRecord.summary.ilike(pattern)) | (FindingRecord.finding_type.ilike(pattern)))
            total = int((await session.scalar(count_stmt)) or 0)
            rows = (await session.scalars(stmt.order_by(FindingRecord.finding_id.desc()).offset(offset).limit(limit))).all()
            return {"items": [self._finding_dict(row) for row in rows], "offset": offset, "limit": limit,
                    "total": total, "next_offset": offset + len(rows) if offset + len(rows) < total else None}

    async def get_finding(self, finding_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = await session.get(FindingRecord, finding_id)
            return self._finding_dict(row) if row else None

    async def list_policy_documents(self, *, offset: int, limit: int, query: str | None = None) -> dict[str, Any]:
        async with self.sessions() as session:
            stmt = select(PolicyDocumentRecord)
            count_stmt = select(func.count()).select_from(PolicyDocumentRecord)
            if query:
                pattern = f"%{query}%"
                criterion = (PolicyDocumentRecord.document_id.ilike(pattern)) | (PolicyDocumentRecord.source.ilike(pattern))
                stmt, count_stmt = stmt.where(criterion), count_stmt.where(criterion)
            total = int((await session.scalar(count_stmt)) or 0)
            rows = (await session.scalars(stmt.order_by(PolicyDocumentRecord.updated_at.desc()).offset(offset).limit(limit))).all()
            items = [{"document_id": r.document_id, "version": r.version, "status": r.status,
                      "access_classification": r.access_classification, "source": r.source,
                      "content_sha256": r.content_sha256, "updated_at": r.updated_at.isoformat(),
                      "metadata": r.metadata_payload} for r in rows]
            return {"items": items, "offset": offset, "limit": limit, "total": total,
                    "next_offset": offset + len(items) if offset + len(items) < total else None}

    @staticmethod
    def _run_dict(row: AnalysisRunRecord) -> dict[str, Any]:
        return {"run_id": row.run_id, "execution_id": row.execution_id, "scenario_id": row.scenario_id,
                "status": row.status, "workflow_status": row.workflow_status, "planner_mode": row.planner_mode,
                "request": row.request_payload, "result": row.result_payload,
                "error_codes": row.error_codes or [], "started_at": row.started_at.isoformat(),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None}

    @staticmethod
    def _finding_dict(row: FindingRecord) -> dict[str, Any]:
        return {"finding_id": row.finding_id, "run_id": row.run_id, "execution_id": row.execution_id,
                "finding_type": row.finding_type, "assessment": row.assessment, "severity": row.severity,
                "classification": row.classification, "status": row.status, "summary": row.summary,
                "finding": row.payload}

    @staticmethod
    def _evidence_dict(row: EvidenceReferenceRecord) -> dict[str, Any]:
        return {"run_id": row.run_id, "evidence_id": row.evidence_id, "kind": row.kind,
                "sha256": row.sha256, "recorded_at": row.recorded_at.isoformat(),
                "source_document_id": row.source_document_id, "classification": row.classification}

    @staticmethod
    def _user_dict(row: UserRecord) -> dict[str, Any]:
        return {"user_id": row.user_id, "google_subject": row.google_subject, "email": row.email,
                "name": row.display_name, "role": row.role, "active": row.active,
                "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
                "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None}
