"""license create table — 已签发 license 记录

Revision ID: 000004
Revises: 000003
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000004"
down_revision = "000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "licenses",
        sa.Column("license_id", sa.String(64), primary_key=True),
        sa.Column("customer_id", sa.String(128), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("binding", sa.String(16), nullable=False),
        sa.Column("bound_fingerprint", sa.String(128), nullable=True),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("signing_key_id", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("limits", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("forge_file", sa.LargeBinary(), nullable=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_licenses_customer_id", "licenses", ["customer_id"])
    op.create_index("ix_licenses_product_id", "licenses", ["product_id"])
    op.create_index("ix_licenses_expires_at", "licenses", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_licenses_expires_at", table_name="licenses")
    op.drop_index("ix_licenses_product_id", table_name="licenses")
    op.drop_index("ix_licenses_customer_id", table_name="licenses")
    op.drop_table("licenses")
