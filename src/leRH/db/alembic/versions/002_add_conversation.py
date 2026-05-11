"""Add conversation_state to users, create messages table

Revision ID: 002
Revises: 001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("conversation_state", sa.String(50), server_default="new"))
    op.execute("UPDATE users SET conversation_state = 'new' WHERE conversation_state IS NULL")
    op.create_table(
        "messages",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="whatsapp"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_column("users", "conversation_state")
