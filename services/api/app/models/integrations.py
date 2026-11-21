"""Connected accounts (Google), sync logs, notifications, push subscriptions, briefings."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ConnectedAccount(UUIDPk, CreatedAt, Base):
    """An OAuth connection. Tokens are encrypted with the account id as associated data.
    status is 'connected' only after a real test call succeeded."""

    __tablename__ = "connected_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('connected','error','revoked')", name="status"),
        UniqueConstraint("user_id", "provider", "account_email", name="uq_connected_account"),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    access_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="connected")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class IntegrationSyncLog(UUIDPk, Base):
    __tablename__ = "integration_sync_logs"

    user_id: Mapped[uuid.UUID] = _user_fk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connected_accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # gmail, calendar
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDPk, CreatedAt, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # briefing, approval, ...
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed: Mapped[bool] = mapped_column(nullable=False, default=False)


class PushSubscription(UUIDPk, CreatedAt, Base):
    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = _user_fk()
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400))


class Briefing(UUIDPk, CreatedAt, Base):
    """A generated briefing or report. data holds the real facts it was written from."""

    __tablename__ = "briefings"
    __table_args__ = (
        CheckConstraint("kind IN ('morning','weekly_status')", name="kind"),
        UniqueConstraint("user_id", "kind", "for_date", name="uq_briefing_day"),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    model: Mapped[str | None] = mapped_column(String(100))  # None = written without a model
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
