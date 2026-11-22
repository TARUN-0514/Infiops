"""Personal life: goals, routines, lists, journal and important dates."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk
from app.db.encrypted import EncryptedText

GOAL_AREAS = ("personal", "career", "health", "money", "learning", "relationships")


def _user() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Goal(UUIDPk, CreatedAt, Base):
    """A goal with optional milestones ([{"title", "done"}]); progress follows the milestones
    when there are any, otherwise the owner sets it."""

    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("status IN ('active','done','dropped')", name="status"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress"),
        CheckConstraint(f"area IN ({', '.join(repr(a) for a in GOAL_AREAS)})", name="area"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    area: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    why: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="active")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    milestones: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class Routine(UUIDPk, CreatedAt, Base):
    """A checklist done on certain weekdays (0 = Monday)."""

    __tablename__ = "routines"
    __table_args__ = (
        CheckConstraint("time_of_day IN ('morning','afternoon','evening','any')", name="time"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(10), nullable=False, default="any")
    steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    weekdays: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RoutineLog(Base):
    """Which steps were done on a day."""

    __tablename__ = "routine_logs"

    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routines.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    done_steps: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)


class PersonalList(UUIDPk, CreatedAt, Base):
    __tablename__ = "lists"
    __table_args__ = (
        CheckConstraint("kind IN ('checklist','shopping','reading','travel','ideas')", name="kind"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="checklist")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ListItem(UUIDPk, CreatedAt, Base):
    __tablename__ = "list_items"
    __table_args__ = (Index("ix_list_items_list_position", "list_id", "position"),)

    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class JournalEntry(UUIDPk, CreatedAt, Base):
    """Private writing: the text is encrypted and only the local model reads it."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint("mood IS NULL OR mood BETWEEN 1 AND 5", name="mood"),
        Index("ix_journal_entries_user_day", "user_id", "day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    mood: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(EncryptedText("journal_entries.content"), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class ImportantDate(UUIDPk, CreatedAt, Base):
    """A yearly date (birthday, anniversary) or a one-off (passport renewal). `year` is the
    birth or start year for yearly dates, or the year of a one-off date."""

    __tablename__ = "important_dates"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('birthday','anniversary','renewal','deadline','other')", name="kind"
        ),
        CheckConstraint("month BETWEEN 1 AND 12 AND day BETWEEN 1 AND 31", name="date"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="birthday")
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    yearly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remind_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    notes: Mapped[str | None] = mapped_column(String(500))
    last_reminded_on: Mapped[date | None] = mapped_column(Date)
