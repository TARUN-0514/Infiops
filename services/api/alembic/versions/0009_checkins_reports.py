"""midday and evening check-ins, monthly reports

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-22 09:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = "kind IN ('morning','midday','evening','weekly_status','monthly')"
OLD = "kind IN ('morning','weekly_status')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_briefings_kind"), "briefings", type_="check")
    op.create_check_constraint(op.f("ck_briefings_kind"), "briefings", NEW)


def downgrade() -> None:
    op.execute("DELETE FROM briefings WHERE kind IN ('midday','evening','monthly')")
    op.drop_constraint(op.f("ck_briefings_kind"), "briefings", type_="check")
    op.create_check_constraint(op.f("ck_briefings_kind"), "briefings", OLD)
