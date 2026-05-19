"""signing_key create table — 签名密钥元数据（密钥本体在 key_storage 后端）

Revision ID: 000005
Revises: 000004
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000005"
down_revision = "000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signing_keys",
        sa.Column("key_id", sa.String(64), primary_key=True),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_locator", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
        # 注意：private_key 字段不入库 —— 本表只存元数据 + 公钥
    )
    op.create_index("ix_signing_keys_algorithm_status", "signing_keys", ["algorithm", "status"])


def downgrade() -> None:
    op.drop_index("ix_signing_keys_algorithm_status", table_name="signing_keys")
    op.drop_table("signing_keys")
