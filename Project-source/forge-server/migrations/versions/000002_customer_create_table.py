"""customer create table — 客户实体（购买 license 的对端）

Revision ID: 000002
Revises: 000001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000002"
down_revision = "000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("contact_email", sa.String(256), nullable=False, server_default=""),
        sa.Column("contact_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("region", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customers_status", "customers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_customers_status", table_name="customers")
    op.drop_table("customers")
