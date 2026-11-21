"""Long-term memory: versioned items with sources, confidence and privacy labels."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk

EMBEDDING_DIM = 1024  # bge-m3

MEMORY_KINDS = ("episodic", "semantic", "procedural")
MEMORY_CATEGORIES = (
    "profile",
    "preference",
    "work",
    "people",
    "health",
    "finance",
    "goal",
    "routine",
    "other",
)
MEMORY_STATUSES = ("active", "inferred", "superseded")
PRIVACY_LEVELS = ("normal", "sensitive", "secret")


def _in(values: tuple[str, ...]) -> str:
    return ",".join(f"'{v}'" for v in values)


class MemoryItem(UUIDPk, CreatedAt, Base):
    """Never edited in place: a change writes a new version and marks the old one
    superseded. `inferred` items wait for the owner's confirmation."""

    __tablename__ = "memory_items"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(MEMORY_KINDS)})", name="kind"),
        CheckConstraint(f"category IN ({_in(MEMORY_CATEGORIES)})", name="category"),
        CheckConstraint(f"status IN ({_in(MEMORY_STATUSES)})", name="status"),
        CheckConstraint(f"privacy IN ({_in(PRIVACY_LEVELS)})", name="privacy"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        Index("ix_memory_items_search", "search", postgresql_using="gin"),
        Index("ix_memory_items_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="semantic")
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    privacy: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="SET NULL")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )


class MemorySource(UUIDPk, CreatedAt, Base):
    """Where a memory came from: a chat message, a manual entry, an import."""

    __tablename__ = "memory_sources"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(80))
    excerpt: Mapped[str | None] = mapped_column(Text)


class MemoryConflict(UUIDPk, CreatedAt, Base):
    """A new fact that may contradict an existing memory, waiting for the owner."""

    __tablename__ = "memory_conflicts"
    __table_args__ = (CheckConstraint("status IN ('open','resolved')", name="status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False
    )
    candidate: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    resolution: Mapped[str | None] = mapped_column(String(16))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["EMBEDDING_DIM", "MemoryConflict", "MemoryItem", "MemorySource"]
