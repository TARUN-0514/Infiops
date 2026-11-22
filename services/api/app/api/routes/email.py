"""Emails: synced Gmail with triage, AI drafts, approved sending and follow-ups."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.ai.gateway import get_gateway
from app.ai.orchestrator import approval_out
from app.ai.tools.builtin import get_registry
from app.ai.types import BudgetExceededError, ModelRefusalError, ModelUnavailableError
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import EmailDraft, EmailMessage
from app.services import approvals
from app.services import email as mail
from app.services import integrations as integ

router = APIRouter(prefix="/email", tags=["email"])

MODEL_ERRORS = (ModelUnavailableError, BudgetExceededError, ModelRefusalError)


def message_out(m: EmailMessage, full: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(m.id),
        "thread_id": m.thread_id,
        "from_name": m.from_name,
        "from_addr": m.from_addr,
        "to": m.to_addrs,
        "subject": m.subject,
        "snippet": m.snippet,
        "received_at": m.received_at.isoformat(),
        "is_unread": m.is_unread,
        "labels": m.labels,
        "category": m.category,
        "priority": m.priority,
        "needs_reply": m.needs_reply and m.replied_at is None,
        "summary": m.summary,
        "triaged": m.triaged_at is not None,
        "replied_at": m.replied_at.isoformat() if m.replied_at else None,
    }
    if full:
        out["cc"] = m.cc_addrs
        out["body_text"] = m.body_text
    return out


def draft_out(d: EmailDraft) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "reply_to_id": str(d.reply_to_id) if d.reply_to_id else None,
        "to": d.to_addrs,
        "cc": d.cc_addrs,
        "subject": d.subject,
        "body": d.body,
        "status": d.status,
        "source": d.source,
        "approval_id": str(d.approval_id) if d.approval_id else None,
        "error": d.error,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        "updated_at": d.updated_at.isoformat(),
    }


@router.get("/summary")
async def summary(db: DB, auth: Auth) -> dict[str, Any]:
    account = await integ.google_account(db, auth.user.id)
    broken = None
    if account is None:
        broken = next(
            (a for a in await integ.list_accounts(db, auth.user.id) if a.provider == "google"),
            None,
        )
    return {
        "connected": account is not None,
        "account_error": broken.last_error or "Reconnect Google." if broken else None,
        "account_email": account.account_email if account else None,
        "last_sync_at": account.last_sync_at.isoformat()
        if account and account.last_sync_at
        else None,
        **await mail.counts(db, auth.user.id),
    }


@router.get("/messages")
async def list_messages(
    db: DB,
    auth: Auth,
    view: Literal["inbox", "needs_reply", "important", "sent", "all"] = "inbox",
    category: str | None = None,
    q: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    rows = await mail.list_messages(
        db, auth.user.id, view=view, category=category, q=q, limit=limit, offset=offset
    )
    return [message_out(m) for m in rows]


async def _message(db: DB, auth: Auth, mid: uuid.UUID) -> EmailMessage:
    try:
        return await mail.get_owned_message(db, auth.user.id, mid)
    except LookupError:
        not_found("Email not found.")


async def _draft(db: DB, auth: Auth, did: uuid.UUID) -> EmailDraft:
    try:
        d = await mail.get_owned_draft(db, auth.user.id, did)
    except LookupError:
        not_found("Draft not found.")
    await mail.unlock_if_stale(db, d)
    return d


@router.get("/messages/{mid}")
async def get_message(mid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    m = await _message(db, auth, mid)
    drafts = await db.scalars(
        select(EmailDraft)
        .where(EmailDraft.reply_to_id == m.id, EmailDraft.status != "discarded")
        .order_by(EmailDraft.created_at.desc())
    )
    thread = await db.scalars(
        select(EmailMessage)
        .where(EmailMessage.user_id == auth.user.id, EmailMessage.thread_id == m.thread_id)
        .order_by(EmailMessage.received_at)
    )
    return {
        **message_out(m, full=True),
        "drafts": [draft_out(d) for d in drafts],
        "thread": [message_out(t) for t in thread if t.id != m.id],
    }


@router.post("/sync")
async def sync(db: DB, auth: Auth) -> dict[str, Any]:
    from app.worker import run_account_sync

    account = await integ.google_account(db, auth.user.id)
    if account is None:
        bad_request("Connect Google in Settings › Integrations first.", code="not_connected")
    result = await run_account_sync(db, account)
    await db.commit()
    return result


@router.post("/triage")
async def triage(db: DB, auth: Auth) -> dict[str, int]:
    try:
        done = await mail.triage(db, get_gateway(), auth.user)
    except MODEL_ERRORS as exc:
        await db.commit()
        bad_request(str(exc), code="model_unavailable")
    await db.commit()
    return {"triaged": done}


class DraftAiIn(BaseModel):
    instructions: str = Field("", max_length=2000)
    cloud: bool = False


@router.post("/messages/{mid}/draft", status_code=201)
async def ai_draft(mid: uuid.UUID, body: DraftAiIn, db: DB, auth: Auth) -> dict[str, Any]:
    m = await _message(db, auth, mid)
    try:
        d = await mail.draft_reply(
            db, get_gateway(), auth.user, m, instructions=body.instructions, cloud=body.cloud
        )
    except MODEL_ERRORS as exc:
        await db.commit()
        bad_request(str(exc), code="model_unavailable")
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    return draft_out(d)


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply_to_id: uuid.UUID | None = None
    to: list[EmailStr] = Field(default_factory=list, max_length=20)
    cc: list[EmailStr] = Field(default_factory=list, max_length=20)
    subject: str = Field("", max_length=500)
    body: str = Field("", max_length=50_000)


@router.post("/drafts", status_code=201)
async def create_draft(body: DraftIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        account = await integ.require_google(db, auth.user.id)
    except ValueError as exc:
        bad_request(str(exc), code="not_connected")
    reply = await _message(db, auth, body.reply_to_id) if body.reply_to_id else None
    d = EmailDraft(
        user_id=auth.user.id,
        account_id=reply.account_id if reply else account.id,
        reply_to_id=reply.id if reply else None,
        to_addrs=[str(x).lower() for x in body.to] or ([reply.from_addr] if reply else []),
        cc_addrs=[str(x).lower() for x in body.cc],
        subject=body.subject or (f"Re: {reply.subject}" if reply else ""),
        body=body.body,
    )
    db.add(d)
    await db.commit()
    return draft_out(d)


@router.get("/drafts")
async def list_drafts(
    db: DB,
    auth: Auth,
    status_: Literal["open", "sent", "all"] = Query("open", alias="status"),
) -> list[dict[str, Any]]:
    stmt = select(EmailDraft).where(EmailDraft.user_id == auth.user.id)
    if status_ == "open":
        stmt = stmt.where(EmailDraft.status.in_(["draft", "pending_approval", "failed"]))
    elif status_ == "sent":
        stmt = stmt.where(EmailDraft.status == "sent")
    rows = await db.scalars(stmt.order_by(EmailDraft.updated_at.desc()).limit(100))
    return [draft_out(d) for d in rows]


class DraftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: list[EmailStr] | None = Field(None, max_length=20)
    cc: list[EmailStr] | None = Field(None, max_length=20)
    subject: str | None = Field(None, max_length=500)
    body: str | None = Field(None, max_length=50_000)


@router.patch("/drafts/{did}")
async def update_draft(did: uuid.UUID, body: DraftPatch, db: DB, auth: Auth) -> dict[str, Any]:
    d = await _draft(db, auth, did)
    if d.status not in ("draft", "failed"):
        bad_request(
            "This draft is waiting for approval or already sent. Reject the request to edit it.",
            code="locked",
        )
    if body.to is not None:
        d.to_addrs = [str(x).lower() for x in body.to]
    if body.cc is not None:
        d.cc_addrs = [str(x).lower() for x in body.cc]
    if body.subject is not None:
        d.subject = body.subject
    if body.body is not None:
        d.body = body.body
    d.status, d.updated_at = "draft", datetime.now(d.updated_at.tzinfo)
    await db.commit()
    return draft_out(d)


@router.delete("/drafts/{did}", status_code=204)
async def discard_draft(did: uuid.UUID, db: DB, auth: Auth) -> None:
    d = await _draft(db, auth, did)
    if d.status == "sent":
        bad_request("A sent email can't be discarded.")
    if d.status == "pending_approval":
        bad_request("Reject the approval request first.", code="locked")
    if d.provider_draft_id:
        account = await integ.google_account(db, auth.user.id)
        if account is not None:
            try:
                await integ.client(account).gmail_delete_draft(d.provider_draft_id)
            except Exception:  # noqa: S110 - the Gmail copy may already be gone
                pass
    d.status = "discarded"
    await db.commit()


@router.post("/drafts/{did}/save-to-gmail")
async def save_to_gmail(did: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    d = await _draft(db, auth, did)
    try:
        await mail.push_draft(db, d)
    except Exception as exc:
        bad_request(f"Gmail didn't save the draft: {exc}")
    await db.commit()
    return draft_out(d)


@router.post("/drafts/{did}/send")
async def request_send(did: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    """Asks for approval. Nothing is sent until the owner approves the request."""
    d = await _draft(db, auth, did)
    if d.status not in ("draft", "failed"):
        bad_request(f"This draft is {d.status.replace('_', ' ')}.", code="bad_state")
    if not d.to_addrs:
        bad_request("Add at least one recipient.")
    if not d.body.strip():
        bad_request("The email is empty.")
    approval = await approvals.request(
        db, get_registry(), auth.user, "email_send", {"draft_id": str(d.id)}
    )
    recipients = ", ".join(d.to_addrs[:3]) + (" and others" if len(d.to_addrs) > 3 else "")
    approval.summary = f"Send “{d.subject or '(no subject)'}” to {recipients}"[:500]
    d.status, d.approval_id, d.error = "pending_approval", approval.id, None
    await db.commit()
    return {"draft": draft_out(d), "approval": approval_out(approval)}


class FollowUpIn(BaseModel):
    days: int = Field(3, ge=1, le=60)


@router.post("/messages/{mid}/follow-up", status_code=201)
async def follow_up(mid: uuid.UUID, body: FollowUpIn, db: DB, auth: Auth) -> dict[str, Any]:
    m = await _message(db, auth, mid)
    t = await mail.follow_up(db, auth.user, m, body.days)
    await db.commit()
    return {
        "task_id": str(t.id),
        "title": t.title,
        "due_at": t.due_at.isoformat() if t.due_at else None,
    }


class TriagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    needs_reply: bool | None = None
    priority: Literal["low", "normal", "high"] | None = None
    category: Literal["action", "reply", "fyi", "newsletter", "promotion", "other"] | None = None


@router.patch("/messages/{mid}")
async def correct_triage(mid: uuid.UUID, body: TriagePatch, db: DB, auth: Auth) -> dict[str, Any]:
    """The owner corrects the model's triage."""
    m = await _message(db, auth, mid)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    await db.commit()
    return message_out(m)
