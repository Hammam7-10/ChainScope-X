"""Create R5 relational persistence tables.

Revision ID: 20261114_01
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261114_01"
down_revision = None
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("execution_id", sa.String(length=128), nullable=True),
        sa.Column("scenario_id", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workflow_status", sa.String(length=32), nullable=True),
        sa.Column("planner_mode", sa.String(length=16), nullable=True),
        sa.Column("request_payload", JSON_TYPE, nullable=False),
        sa.Column("result_payload", JSON_TYPE, nullable=True),
        sa.Column("retry_payload", JSON_TYPE, nullable=True),
        sa.Column("error_codes", JSON_TYPE, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING','PERSISTENCE_PENDING','COMPLETED','REJECTED','FAILED')",
                           name="ck_analysis_run_status"),
    )
    op.create_index("ix_analysis_runs_execution_id", "analysis_runs", ["execution_id"], unique=True)
    op.create_index("ix_analysis_runs_scenario_id", "analysis_runs", ["scenario_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    op.create_table(
        "findings",
        sa.Column("finding_id", sa.String(length=128), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.String(length=128), nullable=False),
        sa.Column("finding_type", sa.String(length=128), nullable=False),
        sa.Column("assessment", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("classification", sa.String(length=24), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.UniqueConstraint("finding_id", "run_id", name="uq_finding_run_pair"),
        sa.CheckConstraint("assessment IN ('CONFIRMED_VIOLATION','POTENTIAL_RISK','EFFECT_MISMATCH','INCONCLUSIVE','NO_VIOLATION_OBSERVED')",
                           name="ck_finding_assessment"),
        sa.CheckConstraint("severity IN ('CRITICAL','HIGH','MEDIUM','LOW','INFORMATIONAL')",
                           name="ck_finding_severity"),
        sa.CheckConstraint("classification IS NULL OR classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
                           name="ck_finding_classification"),
        sa.CheckConstraint("length(status) > 0", name="ck_finding_nonempty_status"),
    )
    op.create_index("ix_findings_run_id", "findings", ["run_id"])
    op.create_index("ix_findings_execution_id", "findings", ["execution_id"])
    op.create_index("ix_findings_assessment", "findings", ["assessment"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_classification", "findings", ["classification"])
    op.create_index("ix_findings_status", "findings", ["status"])
    op.create_index("ix_findings_run_severity_assessment", "findings", ["run_id", "severity", "assessment"])

    op.create_table(
        "evidence_references",
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("evidence_id", sa.String(length=160), primary_key=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_document_id", sa.String(length=160), nullable=True),
        sa.Column("classification", sa.String(length=24), nullable=True),
        sa.CheckConstraint("classification IS NULL OR classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
                           name="ck_evidence_classification"),
    )
    op.create_table(
        "finding_evidence_links",
        sa.Column("finding_id", sa.String(length=128), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.String(length=160), primary_key=True),
        sa.ForeignKeyConstraint(["finding_id", "run_id"], ["findings.finding_id", "findings.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id", "evidence_id"],
                                ["evidence_references.run_id", "evidence_references.evidence_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_finding_evidence_links_run_id", "finding_evidence_links", ["run_id"])
    op.create_index("ix_finding_evidence_links_evidence_id", "finding_evidence_links", ["evidence_id"])

    op.create_table(
        "policy_documents",
        sa.Column("document_id", sa.String(length=160), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("access_classification", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_payload", JSON_TYPE, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','OBSOLETE','INDEXING_PENDING','DEACTIVATION_PENDING')",
                           name="ck_policy_document_status"),
        sa.CheckConstraint("access_classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
                           name="ck_policy_document_classification"),
    )
    op.create_index("ix_policy_documents_status", "policy_documents", ["status"])
    op.create_index("ix_policy_documents_access_classification", "policy_documents", ["access_classification"])


def downgrade() -> None:
    op.drop_index("ix_policy_documents_access_classification", table_name="policy_documents")
    op.drop_index("ix_policy_documents_status", table_name="policy_documents")
    op.drop_table("policy_documents")
    op.drop_index("ix_finding_evidence_links_evidence_id", table_name="finding_evidence_links")
    op.drop_index("ix_finding_evidence_links_run_id", table_name="finding_evidence_links")
    op.drop_table("finding_evidence_links")
    op.drop_table("evidence_references")
    op.drop_index("ix_findings_run_severity_assessment", table_name="findings")
    op.drop_index("ix_findings_status", table_name="findings")
    op.drop_index("ix_findings_classification", table_name="findings")
    op.drop_index("ix_findings_severity", table_name="findings")
    op.drop_index("ix_findings_assessment", table_name="findings")
    op.drop_index("ix_findings_execution_id", table_name="findings")
    op.drop_index("ix_findings_run_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_scenario_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_execution_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
