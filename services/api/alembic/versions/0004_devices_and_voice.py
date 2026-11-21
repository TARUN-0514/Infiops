"""devices and voice: device settings and the session a paired device signs in with

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21 19:01:25.443567

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("devices", sa.Column("session_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_devices_session_id"), "devices", ["session_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_devices_session_id_user_sessions"),
        "devices",
        "user_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_devices_session_id_user_sessions"), "devices", type_="foreignkey")
    op.drop_index(op.f("ix_devices_session_id"), table_name="devices")
    op.drop_column("devices", "session_id")
    op.drop_column("devices", "settings")
