"""Add credits to User model

Revision ID: 004_add_credits
Revises: 6e95df7f968f_add_source_fields_to_jobs
Create Date: 2026-05-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_add_credits"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("credits", sa.Integer(), nullable=False, server_default="20"))


def downgrade() -> None:
    op.drop_column("users", "credits")
