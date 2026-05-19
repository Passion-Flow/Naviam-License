"""heartbeat_logs + heartbeat_nonces create table — Verifier 心跳

Revision ID: 000008
Revises: 000007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000008"
down_revision = "000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "heartbeat_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("license_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("api_key_id", sa.String(64), nullable=True),
        sa.Column("verifier_version", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_heartbeat_logs_license_received",
        "heartbeat_logs",
        ["license_id", "received_at"],
    )

    op.create_table(
        "heartbeat_nonces",
        sa.Column("license_id", sa.String(64), primary_key=True),
        sa.Column("nonce", sa.String(128), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_heartbeat_nonces_seen_at", "heartbeat_nonces", ["seen_at"])


def downgrade() -> None:
    op.drop_index("ix_heartbeat_nonces_seen_at", table_name="heartbeat_nonces")
    op.drop_table("heartbeat_nonces")
    op.drop_index("ix_heartbeat_logs_license_received", table_name="heartbeat_logs")
    op.drop_table("heartbeat_logs")
