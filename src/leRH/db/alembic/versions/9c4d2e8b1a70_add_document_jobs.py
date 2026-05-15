"""add document generation job status table

Revision ID: 9c4d2e8b1a70
Revises: 7b1f2a0d6c3e
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4d2e8b1a70"
down_revision: str | None = "7b1f2a0d6c3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_jobs",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("job_id", sa.String(length=12), nullable=True),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="telegram"),
        sa.Column("chat_id", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("target_profile", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_document_jobs_job_id_jobs")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_document_jobs_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_jobs")),
    )


def downgrade() -> None:
    op.drop_table("document_jobs")
