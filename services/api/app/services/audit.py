import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ToolExecution


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


# Every run of these is written to audit_logs, whichever path ran it (chat, an approval
# card, an automation) and whether it succeeded. Tool input is not copied: it can hold
# email bodies or file contents, and tool_executions already keeps it.
AUDITED_RISKS = frozenset({"sensitive", "irreversible", "forbidden"})


def tool_run(db: AsyncSession, user_id: uuid.UUID, exe: ToolExecution, *, via: str) -> None:
    if exe.risk not in AUDITED_RISKS:
        return
    record(
        db,
        "tool.denied" if exe.status == "denied" else "tool.executed",
        user_id=user_id,
        actor="assistant",
        target=exe.tool_name,
        risk=exe.risk,
        status=exe.status,
        via=via,
        execution=str(exe.id) if exe.id else None,
        error=(exe.error or "")[:200] or None,
    )
