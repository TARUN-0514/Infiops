"""Research reports: a question, the pages read, and findings labelled by how well they're
supported."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk


class ResearchReport(UUIDPk, CreatedAt, Base):
    __tablename__ = "research_reports"
    __table_args__ = (CheckConstraint("status IN ('running','done','failed')", name="status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    cloud: Mapped[bool] = mapped_column(nullable=False, default=False)
    summary: Mapped[str | None] = mapped_column(Text)
    # [{claim, label: verified|assumption|opinion, sources: [n], note}]
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # [{n, url, title, read: bool}]
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    queries: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
