"""Fitness and habits: workouts with sets, body metrics, food, water, sleep and habits.
Health values are encrypted. Nothing here is medical advice."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk
from app.db.encrypted import EncryptedDecimal, EncryptedText


def _user() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Exercise(UUIDPk, CreatedAt, Base):
    """The owner's own exercises; the built-in library lives in code (services/fitness.py)."""

    __tablename__ = "exercises"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_exercises_user_name"),)

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    muscle: Mapped[str] = mapped_column(String(30), nullable=False, default="Other")
    equipment: Mapped[str] = mapped_column(String(30), nullable=False, default="Other")


class WorkoutSession(UUIDPk, CreatedAt, Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (Index("ix_workout_sessions_user_day", "user_id", "day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False, default="Workout")
    minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(EncryptedText("workout_sessions.notes"))


class WorkoutSet(UUIDPk, Base):
    __tablename__ = "workout_sets"
    __table_args__ = (CheckConstraint("reps IS NULL OR reps BETWEEN 0 AND 1000", name="reps"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    exercise: Mapped[str] = mapped_column(String(80), nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(EncryptedDecimal("workout_sets.weight_kg"))
    seconds: Mapped[int | None] = mapped_column(Integer)  # timed sets: plank, run
    distance_km: Mapped[Decimal | None] = mapped_column(
        EncryptedDecimal("workout_sets.distance_km")
    )


class HealthLog(UUIDPk, CreatedAt, Base):
    """One measurement: body weight, body fat, waist, calories, protein, water or sleep."""

    __tablename__ = "health_logs"
    __table_args__ = (
        CheckConstraint(
            "metric IN ('weight_kg','body_fat_pct','waist_cm','calories','protein_g',"
            "'water_ml','sleep_hours')",
            name="metric",
        ),
        Index("ix_health_logs_user_metric_day", "user_id", "metric", "day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[Decimal] = mapped_column(EncryptedDecimal("health_logs.value"), nullable=False)
    note: Mapped[str | None] = mapped_column(EncryptedText("health_logs.note"))
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")


class Habit(UUIDPk, CreatedAt, Base):
    __tablename__ = "habits"
    __table_args__ = (CheckConstraint("per_week BETWEEN 1 AND 7", name="per_week"),)

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    per_week: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    archived: Mapped[bool] = mapped_column(nullable=False, default=False)


class HabitLog(Base):
    __tablename__ = "habit_logs"

    habit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("habits.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
