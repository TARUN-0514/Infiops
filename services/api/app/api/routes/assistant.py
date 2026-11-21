"""Chat (streamed as NDJSON), approvals, tool permissions, uploads and AI status."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.ai.gateway import get_gateway
from app.ai.orchestrator import Orchestrator, approval_out, message_out
from app.ai.tools.builtin import get_registry
from app.ai.tools.registry import DEFAULT_DECISION, clamp, policies
from app.api.deps import DB, Auth, SettingsDep
from app.api.routes.common import bad_request, not_found
from app.core.logging import log
from app.db.session import get_sessionmaker
from app.models import (
    AgentRun,
    ApprovalRequest,
    Conversation,
    EmailDraft,
    Message,
    ModelUsageLog,
    PermissionPolicy,
    ToolExecution,
    Upload,
    User,
)
from app.services import approvals, audit
from app.services.jobs import enqueue
from app.services.storage import ALLOWED_TYPES, get_storage

router = APIRouter(tags=["assistant"])
_background: set[asyncio.Task[None]] = set()


# --- conversations ----------------------------------------------------------------


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


async def _conversation(db: DB, auth: Auth, cid: uuid.UUID) -> Conversation:
    conv = await db.get(Conversation, cid)
    if conv is None or conv.user_id != auth.user.id or conv.archived_at is not None:
        not_found("Conversation not found.")
    return conv


@router.get("/chat/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: DB, auth: Auth, limit: int = Query(50, le=200)
) -> list[Conversation]:
    return list(
        await db.scalars(
            select(Conversation)
            .where(Conversation.user_id == auth.user.id, Conversation.archived_at.is_(None))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    )


@router.post("/chat/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(db: DB, auth: Auth) -> Conversation:
    conv = Conversation(user_id=auth.user.id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/chat/conversations/{cid}")
async def get_conversation(cid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    conv = await _conversation(db, auth, cid)
    msgs = await db.scalars(
        select(Message).where(Message.conversation_id == cid).order_by(Message.created_at)
    )
    pending = await db.scalars(
        select(ApprovalRequest)
        .join(AgentRun, AgentRun.id == ApprovalRequest.run_id)
        .where(AgentRun.conversation_id == cid, ApprovalRequest.status == "pending")
    )
    status_rows = await db.execute(
        select(ToolExecution.tool_use_id, ToolExecution.status)
        .join(AgentRun, AgentRun.id == ToolExecution.run_id)
        .where(AgentRun.conversation_id == cid)
    )
    tool_status = {tid: st for tid, st in status_rows if tid}
    return {
        "conversation": ConversationOut.model_validate(conv).model_dump(mode="json"),
        "messages": [message_out(m, tool_status) for m in msgs if m.role != "tool"],
        "pending_approvals": [approval_out(a) for a in pending],
    }


@router.patch("/chat/conversations/{cid}", response_model=ConversationOut)
async def rename_conversation(
    cid: uuid.UUID, body: ConversationPatch, db: DB, auth: Auth
) -> Conversation:
    conv = await _conversation(db, auth, cid)
    conv.title = body.title.strip()
    await db.commit()
    await db.refresh(conv)
    return conv


@router.delete("/chat/conversations/{cid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(cid: uuid.UUID, db: DB, auth: Auth) -> None:
    conv = await _conversation(db, auth, cid)
    await db.delete(conv)
    await db.commit()


@router.get("/chat/search")
async def search_messages(
    db: DB, auth: Auth, q: str = Query(min_length=2, max_length=200)
) -> list[dict[str, Any]]:
    tsq = func.websearch_to_tsquery("english", q)
    rows = await db.execute(
        select(
            Message,
            Conversation.title,
            func.ts_headline(
                "english", Message.text, tsq, "MaxWords=24, MinWords=8, StartSel=«, StopSel=»"
            ).label("snip"),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.user_id == auth.user.id, Message.search.op("@@")(tsq), Message.role != "tool"
        )
        .order_by(func.ts_rank(Message.search, tsq).desc())
        .limit(30)
    )
    return [
        {
            "message_id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "conversation_title": title,
            "role": m.role,
            "snippet": snip,
            "created_at": m.created_at.isoformat(),
        }
        for m, title, snip in rows
    ]


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=20000)
    upload_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    cloud: bool = False
    privacy: Literal["normal", "sensitive", "secret"] = "normal"
    voice: bool = False  # spoken turn: short plain-speech reply


async def _run_turn(
    user_id: uuid.UUID, cid: uuid.UUID, body: SendIn, queue: asyncio.Queue[dict[str, Any] | None]
) -> None:
    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    try:
        async with get_sessionmaker()() as db:
            user = await db.get(User, user_id)
            conv = await db.get(Conversation, cid)
            assert user is not None and conv is not None
            uploads = [
                u
                for uid in body.upload_ids
                if (u := await db.get(Upload, uid)) is not None and u.user_id == user_id
            ]
            orch = Orchestrator(db, get_gateway(), get_registry(), emit)
            run = await orch.start(
                user,
                conv,
                body.text,
                uploads=uploads,
                privacy=body.privacy,
                cloud=body.cloud,
                voice=body.voice,
            )
            if run.status == "completed":
                await enqueue(
                    "extract_memories",
                    user_id=str(user_id),
                    message_id=run.state["user_message_id"],
                    cloud=body.cloud,
                )
    except Exception:
        log.exception("chat_turn_failed", conversation_id=str(cid))
        await queue.put(
            {
                "type": "error",
                "code": "internal_error",
                "message": "Something went wrong. The error was logged.",
            }
        )
    finally:
        await queue.put(None)


@router.post("/chat/conversations/{cid}/messages")
async def send_message(cid: uuid.UUID, body: SendIn, db: DB, auth: Auth) -> StreamingResponse:
    """Runs one turn and streams events as NDJSON. The run continues even if the client
    disconnects; everything is saved as it happens."""
    await _conversation(db, auth, cid)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    task = asyncio.create_task(_run_turn(auth.user.id, cid, body, queue))
    _background.add(task)
    task.add_done_callback(_background.discard)

    async def stream() -> AsyncIterator[bytes]:
        while (event := await queue.get()) is not None:
            yield (json.dumps(event, default=str) + "\n").encode()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# --- approvals --------------------------------------------------------------------


@router.get("/approvals")
async def list_approvals(
    db: DB,
    auth: Auth,
    status_: Literal["pending", "approved", "rejected", "expired"] | None = Query(
        None, alias="status"
    ),
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    expired = await db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.user_id == auth.user.id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.expires_at < now,
        )
    )
    for a in expired:
        a.status, a.decided_at = "expired", now
    await db.commit()
    stmt = select(ApprovalRequest).where(ApprovalRequest.user_id == auth.user.id)
    if status_:
        stmt = stmt.where(ApprovalRequest.status == status_)
    rows = await db.scalars(stmt.order_by(ApprovalRequest.created_at.desc()).limit(100))
    out = []
    for a in rows:
        item = approval_out(a)
        run = await db.get(AgentRun, a.run_id) if a.run_id else None
        item["conversation_id"] = str(run.conversation_id) if run and run.conversation_id else None
        out.append(item)
    return out


async def _after_direct(db: DB, approval: ApprovalRequest, result: dict[str, Any]) -> None:
    """Keep an email draft's status in step with its approval request."""
    if approval.tool_name != "email_send":
        return
    draft = await db.get(EmailDraft, uuid.UUID(str(approval.input.get("draft_id"))))
    if draft is None or draft.status == "sent":
        return
    if result["status"] == "failed":
        draft.status, draft.error = "failed", result.get("error")
    elif result["status"] == "rejected":
        draft.status, draft.approval_id = "draft", None


class DecideIn(BaseModel):
    approve: bool


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: uuid.UUID, body: DecideIn, db: DB, auth: Auth
) -> dict[str, Any]:
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None or approval.user_id != auth.user.id:
        not_found("Approval not found.")
    if approval.status != "pending":
        bad_request(f"This request is already {approval.status}.", code="already_decided")
    if approval.expires_at < datetime.now(UTC):
        approval.status = "expired"
        await db.commit()
        bad_request("This request expired.", code="expired")
    events: list[dict[str, Any]] = []

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)

    audit.record(
        db,
        "approval.approved" if body.approve else "approval.rejected",
        user_id=auth.user.id,
        target=str(approval.id),
        tool=approval.tool_name,
    )
    if approval.run_id is None:
        # Started from a page (e.g. an email's Send button), not from a chat run.
        result = await approvals.decide(db, get_registry(), auth.user, approval, body.approve)
        await _after_direct(db, approval, result)
        await db.commit()
        await db.refresh(approval)
        return {"approval": approval_out(approval), "message": None, "result": result}
    try:
        await Orchestrator(db, get_gateway(), get_registry(), emit).resume(
            auth.user, approval, body.approve
        )
    except ValueError as exc:
        bad_request(str(exc))
    await db.refresh(approval)
    message = next(
        (e["message"] for e in reversed(events) if e["type"] == "message.completed"), None
    )
    return {"approval": approval_out(approval), "message": message, "events": events}


# --- tools and permissions --------------------------------------------------------


@router.get("/tools")
async def list_tools(db: DB, auth: Auth) -> list[dict[str, Any]]:
    mine = await policies(db, auth.user.id)
    return [
        {
            "name": t.name,
            "description": t.description,
            "risk": t.risk,
            "default": DEFAULT_DECISION[t.risk],
            "policy": mine.get(t.name),
            "effective": clamp(t.risk, mine.get(t.name)),
        }
        for t in get_registry().all()
    ]


class PermissionIn(BaseModel):
    decision: Literal["allow", "ask", "deny", "default"]


@router.put("/tools/{name}/permission")
async def set_permission(name: str, body: PermissionIn, db: DB, auth: Auth) -> dict[str, Any]:
    tool = get_registry().get(name)
    if tool is None:
        not_found("Tool not found.")
    if body.decision == "allow" and tool.risk == "irreversible":
        bad_request("Irreversible actions always ask first.", code="not_allowed")
    row = await db.scalar(
        select(PermissionPolicy).where(
            PermissionPolicy.user_id == auth.user.id, PermissionPolicy.tool_name == name
        )
    )
    if body.decision == "default":
        if row is not None:
            await db.delete(row)
    elif row is None:
        db.add(PermissionPolicy(user_id=auth.user.id, tool_name=name, decision=body.decision))
    else:
        row.decision = body.decision
    audit.record(
        db, "permission.changed", user_id=auth.user.id, target=name, decision=body.decision
    )
    await db.commit()
    policy = None if body.decision == "default" else body.decision
    return {
        "name": name,
        "risk": tool.risk,
        "policy": policy,
        "effective": clamp(tool.risk, policy),
    }


# --- uploads ----------------------------------------------------------------------

MAGIC = {
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
    "image/gif": b"GIF8",
    "application/pdf": b"%PDF",
}


@router.post("/uploads", status_code=201)
async def upload(
    db: DB,
    auth: Auth,
    settings: SettingsDep,
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, Any]:
    ctype = (file.content_type or "").split(";")[0].strip()
    if ctype not in ALLOWED_TYPES:
        bad_request("That file type isn't supported yet.", code="unsupported_type")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        bad_request(f"Files can be up to {settings.max_upload_mb} MB.", code="too_large")
    magic = MAGIC.get(ctype)
    if (magic and not data.startswith(magic)) or (ctype == "image/webp" and data[8:12] != b"WEBP"):
        bad_request("The file doesn't match its type.", code="bad_file")
    key, sha = get_storage().put(str(auth.user.id), data)
    up = Upload(
        user_id=auth.user.id,
        filename=(file.filename or "file")[:255],
        content_type=ctype,
        size=len(data),
        sha256=sha,
        storage_key=key,
    )
    db.add(up)
    await db.commit()
    return {"id": str(up.id), "filename": up.filename, "content_type": ctype, "size": up.size}


# --- AI status and usage ----------------------------------------------------------


@router.get("/ai/status")
async def ai_status(auth: Auth) -> dict[str, Any]:
    return await get_gateway().status()


@router.get("/ai/usage")
async def ai_usage(db: DB, auth: Auth) -> dict[str, Any]:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await db.execute(
        select(
            ModelUsageLog.provider,
            ModelUsageLog.model,
            func.count(),
            func.sum(ModelUsageLog.input_tokens),
            func.sum(ModelUsageLog.output_tokens),
            func.sum(ModelUsageLog.cost_usd),
        )
        .where(ModelUsageLog.user_id == auth.user.id, ModelUsageLog.at >= start)
        .group_by(ModelUsageLog.provider, ModelUsageLog.model)
    )
    gw = get_gateway()
    return {
        "since": start.isoformat(),
        "cloud_tokens_today": await gw.cloud_tokens_today(db, auth.user.id),
        "cloud_daily_token_budget": gw.settings.cloud_daily_token_budget,
        "by_model": [
            {
                "provider": p,
                "model": m,
                "calls": n,
                "input_tokens": int(i or 0),
                "output_tokens": int(o or 0),
                "cost_usd": float(c) if c is not None else None,
            }
            for p, m, n, i, o, c in rows
        ],
    }
