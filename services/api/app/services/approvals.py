"""Approval requests that start from the UI rather than a chat run (for example the
Send button on an email draft). They use the same tool, risk and audit path as chat."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.registry import ToolContext, ToolRegistry
from app.core.config import get_settings
from app.core.logging import log
from app.models import ApprovalRequest, ToolExecution, User
from app.services import audit


async def request(
    db: AsyncSession, registry: ToolRegistry, user: User, tool_name: str, args: dict[str, Any]
) -> ApprovalRequest:
    tool = registry.get(tool_name)
    if tool is None or tool.risk == "forbidden":
        raise ValueError("This action isn't available.")
    parsed = tool.input_model.model_validate(args)
    exe = ToolExecution(
        user_id=user.id,
        run_id=None,
        tool_use_id=None,
        tool_name=tool.name,
        risk=tool.risk,
        input=args,
        status="pending_approval",
    )
    db.add(exe)
    await db.flush()
    approval = ApprovalRequest(
        user_id=user.id,
        run_id=None,
        tool_execution_id=exe.id,
        tool_name=tool.name,
        risk=tool.risk,
        summary=tool.summary(parsed),
        input=args,
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().approval_ttl_hours),
    )
    db.add(approval)
    await db.flush()
    audit.record(db, "approval.requested", user_id=user.id, target=str(approval.id), tool=tool.name)
    return approval


async def decide(
    db: AsyncSession,
    registry: ToolRegistry,
    user: User,
    approval: ApprovalRequest,
    approved: bool,
) -> dict[str, Any]:
    """Run (or reject) a UI-started request. Returns the tool's output or error."""
    exe = await db.get(ToolExecution, approval.tool_execution_id)
    tool = registry.get(approval.tool_name)
    if exe is None or tool is None:
        raise ValueError("Missing tool execution.")
    now = datetime.now(UTC)
    approval.status, approval.decided_at = ("approved" if approved else "rejected"), now
    if not approved:
        exe.status, exe.finished_at = "rejected", now
        if tool.on_reject is not None:
            await tool.on_reject(ToolContext(db, user), tool.input_model.model_validate(exe.input))
        return {"status": "rejected"}
    exe.status = "running"
    try:
        args = tool.input_model.model_validate(exe.input)
        async with db.begin_nested():
            output = await tool.handler(ToolContext(db, user), args)
    except ValidationError as exc:
        exe.status = "failed"
        exe.error = json.dumps(exc.errors(include_url=False, include_context=False))[:2000]
    except (LookupError, ValueError) as exc:
        exe.status, exe.error = "failed", str(exc)
    except Exception as exc:
        log.exception("tool_failed", tool=exe.tool_name)
        exe.status, exe.error = "failed", type(exc).__name__
    else:
        exe.status, exe.output = "succeeded", output
    exe.finished_at = datetime.now(UTC)
    return {"status": exe.status, "output": exe.output, "error": exe.error}
