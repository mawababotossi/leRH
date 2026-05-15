"""add credit transaction audit table

Revision ID: 7b1f2a0d6c3e
Revises: 1acdafcb68bb
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b1f2a0d6c3e"
down_revision: str | None = "1acdafcb68bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_credit_transactions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_transactions")),
    )


def downgrade() -> None:
    op.drop_table("credit_transactions")
