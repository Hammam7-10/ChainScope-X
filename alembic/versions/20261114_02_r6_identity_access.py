"""Add R6 users and role records.

Revision ID: 20261114_02
Revises: 20261114_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261114_02"
down_revision = "20261114_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("google_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="viewer"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("google_subject", name="uq_users_google_subject"),
        sa.CheckConstraint("role IN ('admin','analyst','viewer')", name="ck_user_role"),
    )
    op.create_index("ix_users_google_subject", "users", ["google_subject"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_active", "users", ["active"])


def downgrade() -> None:
    op.drop_index("ix_users_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_google_subject", table_name="users")
    op.drop_table("users")
