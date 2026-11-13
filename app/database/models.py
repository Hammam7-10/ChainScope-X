"""Relational persistence records; domain decisions remain R1/R3 Pydantic contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


JSON_PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class AnalysisRunRecord(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workflow_status: Mapped[str | None] = mapped_column(String(32))
    planner_mode: Mapped[str | None] = mapped_column(String(16))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)
    retry_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)
    error_codes: Mapped[list[str]] = mapped_column(JSON_PAYLOAD, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    findings: Mapped[list["FindingRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    evidence_references: Mapped[list["EvidenceReferenceRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('RUNNING','PERSISTENCE_PENDING','COMPLETED','REJECTED','FAILED')",
                        name="ck_analysis_run_status"),
    )


class FindingRecord(Base):
    __tablename__ = "findings"

    finding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    finding_type: Mapped[str] = mapped_column(String(128), nullable=False)
    assessment: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    classification: Mapped[str | None] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)

    run: Mapped[AnalysisRunRecord] = relationship(back_populates="findings")
    evidence_links: Mapped[list["FindingEvidenceLink"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", overlaps="finding_links,evidence",
    )

    __table_args__ = (
        Index("ix_findings_run_severity_assessment", "run_id", "severity", "assessment"),
        UniqueConstraint("finding_id", "run_id", name="uq_finding_run_pair"),
        CheckConstraint("assessment IN ('CONFIRMED_VIOLATION','POTENTIAL_RISK','EFFECT_MISMATCH','INCONCLUSIVE','NO_VIOLATION_OBSERVED')",
                        name="ck_finding_assessment"),
        CheckConstraint("severity IN ('CRITICAL','HIGH','MEDIUM','LOW','INFORMATIONAL')",
                        name="ck_finding_severity"),
        CheckConstraint("classification IS NULL OR classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
                        name="ck_finding_classification"),
        CheckConstraint("length(status) > 0", name="ck_finding_nonempty_status"),
    )


class EvidenceReferenceRecord(Base):
    __tablename__ = "evidence_references"

    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String(160))
    classification: Mapped[str | None] = mapped_column(String(24))

    run: Mapped[AnalysisRunRecord] = relationship(back_populates="evidence_references")
    finding_links: Mapped[list["FindingEvidenceLink"]] = relationship(
        back_populates="evidence", overlaps="evidence_links,finding",
    )

    __table_args__ = (
        CheckConstraint("classification IS NULL OR classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
                        name="ck_evidence_classification"),
    )


class FindingEvidenceLink(Base):
    __tablename__ = "finding_evidence_links"

    finding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(160), primary_key=True)

    finding: Mapped[FindingRecord] = relationship(back_populates="evidence_links", overlaps="finding_links,evidence")
    evidence: Mapped[EvidenceReferenceRecord] = relationship(overlaps="evidence_links,finding")

    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "run_id"], ["findings.finding_id", "findings.run_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "evidence_id"],
            ["evidence_references.run_id", "evidence_references.evidence_id"],
            ondelete="CASCADE",
        ),
    )


class PolicyDocumentRecord(Base):
    __tablename__ = "policy_documents"

    document_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    access_classification: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','OBSOLETE','INDEXING_PENDING','DEACTIVATION_PENDING')",
                        name="ck_policy_document_status"),
        CheckConstraint("access_classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
                        name="ck_policy_document_classification"),
    )
