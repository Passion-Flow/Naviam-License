"""revocation_entries create table — License 吊销列表（CRL）

Revision ID: 000007
Revises: 000006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000007"
down_revision = "000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 表名与 ORM model (revocation_entries) 对齐
    op.create_table(
        "revocation_entries",
        sa.Column("license_id", sa.String(64), primary_key=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_revocation_entries_revoked_at", "revocation_entries", ["revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_revocation_entries_revoked_at", table_name="revocation_entries")
    op.drop_table("revocation_entries")
