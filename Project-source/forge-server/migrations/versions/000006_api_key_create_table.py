"""api_key create table — Verifier 用 API Key

Revision ID: 000006
Revises: 000005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000006"
down_revision = "000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("key_id", sa.String(64), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("customer_id", sa.String(128), nullable=False),
        sa.Column("project_label", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_customer_id", "api_keys", ["customer_id"])
    op.create_index("ix_api_keys_status", "api_keys", ["status"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_status", table_name="api_keys")
    op.drop_index("ix_api_keys_customer_id", table_name="api_keys")
    op.drop_table("api_keys")
