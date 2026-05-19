"""api_key add expires_at — 给 API Key 加可选过期时间

Revision ID: 000010
Revises: 000009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000010"
down_revision = "000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "expires_at")
