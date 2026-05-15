"""update credit defaults

Revision ID: c1b2a3d4e5f6
Revises: 9c4d2e8b1a70
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1b2a3d4e5f6"
down_revision: str | None = "9c4d2e8b1a70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default="20",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default="10",
        existing_nullable=False,
    )
