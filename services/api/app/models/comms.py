"""Email (synced Gmail messages and drafts) and calendar events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk

EMAIL_CATEGORIES = ("action", "reply", "fyi", "newsletter", "promotion", "other")


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _account_fk(nullable: bool = False) -> Mapped[Any]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connected_accounts.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
    )


class EmailMessage(UUIDPk, CreatedAt, Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "provider_id", name="uq_email_provider"),
        Index("ix_email_user_received", "user_id", "received_at"),
        Index("ix_email_messages_search", "search", postgresql_using="gin"),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rfc_message_id: Mapped[str | None] = mapped_column(String(400))
    from_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    from_addr: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    to_addrs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cc_addrs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    labels: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_unread: Mapped[bool] = mapped_column(nullable=False, default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Triage by the local model. category is None until triaged.
    category: Mapped[str | None] = mapped_column(String(16))
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="normal")
    needs_reply: Mapped[bool] = mapped_column(nullable=False, default=False)
    summary: Mapped[str | None] = mapped_column(Text)
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(subject,'') || ' ' || coalesce(from_name,'') || ' '"
            " || coalesce(from_addr,'') || ' ' || coalesce(body_text,''))",
            persisted=True,
        ),
    )


class EmailDraft(UUIDPk, CreatedAt, Base):
    """A reply or new email. It is sent only through an approved email_send request."""

    __tablename__ = "email_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','pending_approval','sent','failed','discarded')", name="status"
        ),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id", ondelete="SET NULL")
    )
    to_addrs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cc_addrs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")  # ai
    provider_draft_id: Mapped[str | None] = mapped_column(String(64))
    provider_message_id: Mapped[str | None] = mapped_column(String(64))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CalendarEvent(UUIDPk, CreatedAt, Base):
    """A Google Calendar event (account_id set) or a NEXUS-only event (account_id null)."""

    __tablename__ = "calendar_events"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed','tentative','cancelled')", name="status"),
        UniqueConstraint("account_id", "provider_id", name="uq_event_provider"),
        Index("ix_events_user_start", "user_id", "starts_at"),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    account_id: Mapped[uuid.UUID | None] = _account_fk(nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(200))
    calendar_id: Mapped[str] = mapped_column(String(200), nullable=False, default="primary")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(300))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    all_day: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    attendees: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    html_link: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
