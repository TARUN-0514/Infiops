import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record(
    db: AsyncSession,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    actor: str = "user",
    target: str | None = None,
    ip: str | None = None,
    **detail: Any,
) -> None:
    """Add an audit row to the current transaction. Never pass secrets in detail."""
    db.add(
        AuditLog(user_id=user_id, actor=actor, action=action, target=target, ip=ip, detail=detail)
    )
