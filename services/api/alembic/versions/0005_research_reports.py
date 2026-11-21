"""research reports

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21 23:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("cloud", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("queries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running','done','failed')", name=op.f("ck_research_reports_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_research_reports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_reports")),
    )
    op.create_index(
        op.f("ix_research_reports_user_id"), "research_reports", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_research_reports_user_id"), table_name="research_reports")
    op.drop_table("research_reports")
