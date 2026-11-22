"""Security workspaces: vulnerability findings, project boards and the learning track."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk

WORKSPACE_KINDS = ("vulns", "appsec", "cloud", "pentest", "custom")
SEVERITIES = ("critical", "high", "medium", "low", "info")
EVENT_KINDS = ("created", "status", "comment", "escalated", "follow_up", "imported", "reopened")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _user() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Workspace(UUIDPk, CreatedAt, Base):
    """A board. `statuses` are its columns in order; `closed` lists the ones that count as
    done; `fields` are extra fields its items carry; `sla_days` maps severity to days."""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(WORKSPACE_KINDS)})", name="kind"),
        UniqueConstraint("user_id", "name", name="uq_workspaces_user_name"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    statuses: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    closed: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    sla_days: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WorkspaceItem(UUIDPk, CreatedAt, Base):
    """A finding, scan, escalation or project card."""

    __tablename__ = "workspace_items"
    __table_args__ = (
        CheckConstraint(f"severity IN ({_in(SEVERITIES)})", name="severity"),
        UniqueConstraint("workspace_id", "external_key", name="uq_workspace_items_external"),
        Index("ix_workspace_items_ws_status", "workspace_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    asset: Mapped[str | None] = mapped_column(String(300))
    identifier: Mapped[str | None] = mapped_column(String(120))  # CVE, rule id, ticket
    owner: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    found_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_to: Mapped[str | None] = mapped_column(String(120))
    sla_notified_on: Mapped[date | None] = mapped_column(Date)
    external_key: Mapped[str | None] = mapped_column(String(300))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkspaceItemEvent(UUIDPk, CreatedAt, Base):
    """History of an item: status changes, comments, escalations and follow-ups."""

    __tablename__ = "workspace_item_events"
    __table_args__ = (CheckConstraint(f"kind IN ({_in(EVENT_KINDS)})", name="kind"),)

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")


class LearningTrack(UUIDPk, CreatedAt, Base):
    __tablename__ = "learning_tracks"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_learning_tracks_user_name"),)

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    goal: Mapped[str | None] = mapped_column(String(300))
    target_date: Mapped[date | None] = mapped_column(Date)


class LearningTopic(UUIDPk, CreatedAt, Base):
    """A syllabus topic with a spaced-review schedule."""

    __tablename__ = "learning_topics"
    __table_args__ = (
        CheckConstraint("status IN ('todo','learning','done')", name="status"),
        CheckConstraint("confidence BETWEEN 0 AND 5", name="confidence"),
    )

    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="todo")
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review_on: Mapped[date | None] = mapped_column(Date)
    reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LearningSession(UUIDPk, CreatedAt, Base):
    """A study or lab session: the lab log."""

    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint("kind IN ('study','lab','review','exam')", name="kind"),
        CheckConstraint("minutes BETWEEN 1 AND 1440", name="minutes"),
    )

    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_topics.id", ondelete="SET NULL")
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="study")
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    machine: Mapped[str | None] = mapped_column(String(120))  # lab box name
    outcome: Mapped[str | None] = mapped_column(String(30))  # e.g. user, root, stuck
    notes: Mapped[str | None] = mapped_column(Text)
