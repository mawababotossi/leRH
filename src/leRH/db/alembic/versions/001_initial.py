"""Initial migration

Revision ID: 001
Revises:
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("telegram_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("whatsapp_id", sa.String(255), nullable=True, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(100), nullable=False, server_default="Togo"),
        sa.Column("activity", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("diploma", sa.String(255), nullable=True),
        sa.Column("experience", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("languages", sa.JSON(), nullable=True),
        sa.Column("availability", sa.String(50), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("recruiter_id", sa.String(12), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cvs",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("analysis", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("candidate_id", sa.String(12), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.String(12), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("ai_analysis", sa.JSON(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("applications")
    op.drop_table("cvs")
    op.drop_table("jobs")
    op.drop_table("users")
