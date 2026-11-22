"""Automation workflows: a trigger, ordered steps, and runs saved after every step."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk

STEP_KINDS = ("tool", "agent", "condition", "approval", "notify")
RUN_STATUSES = (
    "queued",
    "running",
    "waiting_approval",
    "retrying",
    "succeeded",
    "stopped",
    "failed",
    "cancelled",
)


class AutomationWorkflow(UUIDPk, CreatedAt, Base):
    """trigger is {"type": "manual"}, {"type": "schedule", ...} or
    {"type": "event", "event": ..., "filter": {...}}."""

    __tablename__ = "automation_workflows"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_automation_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_from_prompt: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AutomationStep(UUIDPk, Base):
    __tablename__ = "automation_steps"
    __table_args__ = (
        CheckConstraint(f"kind IN ({', '.join(repr(k) for k in STEP_KINDS)})", name="kind"),
        CheckConstraint("retry_max BETWEEN 0 AND 5", name="retry_max"),
        UniqueConstraint("workflow_id", "ordinal", name="uq_automation_step_ordinal"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    retry_max: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)


class AutomationRun(UUIDPk, Base):
    """One run. `steps` is the step log: [{ordinal, kind, name, status, attempts, output,
    error, started_at, finished_at}]. `cursor` is the next step to run."""

    __tablename__ = "automation_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({', '.join(repr(s) for s in RUN_STATUSES)})", name="status"),
        Index("ix_automation_runs_due", "status", "resume_at"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    resume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
