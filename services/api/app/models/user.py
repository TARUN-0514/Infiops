import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, UUIDPk


class User(UUIDPk, CreatedAt, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('owner','member')", name="role"),)

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="owner")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_pending_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_last_used_step: Mapped[int | None] = mapped_column()  # blocks TOTP replay
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    preferences: Mapped["UserPreferences"] = relationship(back_populates="user", uselist=False)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="dark")
    layout: Mapped[str] = mapped_column(String(16), nullable=False, default="expanded")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped[User] = relationship(back_populates="preferences")


class UserSession(UUIDPk, CreatedAt, Base):
    """One signed-in device/browser. Refresh tokens rotate; reuse of an old one revokes it."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(INET)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(40))


class Device(UUIDPk, CreatedAt, Base):
    """A paired client such as the Windows local agent. It signs in through its own session."""

    __tablename__ = "devices"
    __table_args__ = (CheckConstraint("kind IN ('web','desktop','mobile')", name="kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(32))
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Owner-chosen options for the device, e.g. {"wake_word": false, "hands_free": false}.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL"), index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
