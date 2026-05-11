"""Add subscription model for paid matching notifications

Revision ID: 003
Revises: 6e95df7f968f
Create Date: 2026-05-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "6e95df7f968f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("min_match_score", sa.Float(), nullable=False, server_default=sa.text("60.0")),
        sa.Column("notify_telegram", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("notify_whatsapp", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_notified_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
