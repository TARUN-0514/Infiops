"""Phase 7 security review: every sensitive and irreversible tool, checked on the server.

The risk table is pinned here so a tool can't quietly lose its approval step, and each
path that can run a tool (chat, an approval card, an automation) is shown to ask first,
name what it touches, and leave an audit row."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.ai.providers import ScriptedProvider
from app.ai.tools.builtin import get_registry
from app.ai.tools.registry import DEFAULT_DECISION, clamp
from app.db.session import get_sessionmaker
from app.models import ApprovalRequest, AuditLog
from tests.conftest import FakeGoogle, auth_headers
from tests.test_chat import _conv, _send
from tests.test_google_email import _synced_message

API = "/api/v1"

# Reviewed in Phase 7 (docs/SECURITY-REVIEW.md). Changing a tool's risk means updating
# this table and the review, on purpose.
REVIEWED: dict[str, set[str]] = {
    "irreversible": {"email_send"},
    "sensitive": {
        "browser_act",
        "calendar_create_event",
        "calendar_delete_event",
        "calendar_time_block",
        "calendar_update_event",
        "claude_code_run",
        "computer_use",
        "files_move",
        "files_write",
        "memory_forget",
        "tasks_delete",
    },
    "forbidden": set(),
}

# No tool may move money, change sign-in or security settings, or decide approvals.
BANNED_WORDS = ("pay", "transfer", "password", "mfa", "totp", "permission", "approv", "policy")


async def _audit(action: str) -> list[AuditLog]:
    async with get_sessionmaker()() as db:
        return list(await db.scalars(select(AuditLog).where(AuditLog.action == action)))


def test_risk_levels_are_pinned() -> None:
    tools = get_registry().all()
    for risk, names in REVIEWED.items():
        assert {t.name for t in tools if t.risk == risk} == names, risk


def test_no_tool_touches_money_security_or_approvals() -> None:
    for t in get_registry().all():
        assert not any(w in t.name for w in BANNED_WORDS), t.name


def test_policies_cannot_lift_hard_limits() -> None:
    for t in get_registry().all():
        assert clamp(t.risk, None) == DEFAULT_DECISION[t.risk]
        if t.risk in ("sensitive", "irreversible"):
            assert clamp(t.risk, None) == "ask", t.name
        if t.risk == "irreversible":
            assert {clamp(t.risk, p) for p in ("allow", "ask")} == {"ask"}
    assert {clamp("forbidden", p) for p in ("allow", "ask", "deny", None)} == {"deny"}


def test_sensitive_tools_describe_what_they_touch() -> None:
    """Approval cards for destructive tools look up the real item, not a generic line."""
    reg = get_registry()
    for name in ("email_send", "tasks_delete", "memory_forget", "calendar_delete_event"):
        tool = reg.get(name)
        assert tool is not None and tool.describe is not None, name


async def test_chat_card_names_the_task_and_is_audited(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    task = (await client.post(f"{API}/tasks", json={"title": "File taxes"}, headers=h)).json()
    await client.post(
        f"{API}/tasks", json={"title": "Find Form 16", "parent_task_id": task["id"]}, headers=h
    )
    cid = await _conv(client, h)
    model.push([{"name": "tasks_delete", "input": {"task_id": task["id"]}}])
    events = await _send(client, h, cid, "delete the taxes task")
    approval = next(e for e in events if e["type"] == "approval.required")["approval"]
    assert approval["summary"] == "Delete task “File taxes” and its 1 subtasks"
    assert [a.target for a in await _audit("approval.requested")] == [approval["id"]]
    assert await _audit("tool.executed") == []

    model.push("Deleted.")
    r = await client.post(
        f"{API}/approvals/{approval['id']}/decide", json={"approve": True}, headers=h
    )
    assert r.status_code == 200
    (row,) = await _audit("tool.executed")
    assert row.target == "tasks_delete" and row.actor == "assistant"
    assert row.detail["status"] == "succeeded" and row.detail["via"] == "chat"
    assert "task_id" not in row.detail  # tool input is never copied into the audit log


async def test_owner_allowed_sensitive_tool_still_audited(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    r = await client.put(
        f"{API}/tools/tasks_delete/permission", json={"decision": "allow"}, headers=h
    )
    assert r.json()["effective"] == "allow"
    task = (await client.post(f"{API}/tasks", json={"title": "Old"}, headers=h)).json()
    cid = await _conv(client, h)
    model.push([{"name": "tasks_delete", "input": {"task_id": task["id"]}}], "Gone.")
    events = await _send(client, h, cid, "delete it")
    assert not any(e["type"] == "approval.required" for e in events)
    (row,) = await _audit("tool.executed")
    assert row.target == "tasks_delete" and row.detail["status"] == "succeeded"


async def test_denied_call_is_audited(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    await client.put(
        f"{API}/tools/calendar_delete_event/permission", json={"decision": "deny"}, headers=h
    )
    cid = await _conv(client, h)
    model.push(
        [{"name": "calendar_delete_event", "input": {"event_id": str(uuid.uuid4())}}], "Blocked."
    )
    events = await _send(client, h, cid, "clear my calendar")
    finished = next(e for e in events if e["type"] == "tool.finished")
    assert finished["status"] == "denied"
    (row,) = await _audit("tool.denied")
    assert row.target == "calendar_delete_event"


async def test_send_card_names_recipients_and_locks_the_draft(
    client: AsyncClient, google: FakeGoogle, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    mid = await _synced_message(client, h, google)
    draft = (
        await client.post(
            f"{API}/email/drafts", json={"reply_to_id": mid, "body": "On it."}, headers=h
        )
    ).json()
    cid = await _conv(client, h)
    model.push([{"name": "email_send", "input": {"draft_id": draft["id"]}}])
    events = await _send(client, h, cid, "send it")
    approval = next(e for e in events if e["type"] == "approval.required")["approval"]
    assert approval["summary"] == "Send “Re: Q3 report” to priya@example.com"
    # what was approved can't change underneath the approval
    r = await client.patch(
        f"{API}/email/drafts/{draft['id']}", json={"body": "Changed."}, headers=h
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "locked"
    assert google.sent == []
    # once the request expires, the draft is editable again
    async with get_sessionmaker()() as db:
        await db.execute(
            update(ApprovalRequest).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()
    r = await client.patch(
        f"{API}/email/drafts/{draft['id']}", json={"body": "Changed."}, headers=h
    )
    assert r.status_code == 200 and r.json()["status"] == "draft"


async def test_automation_tool_step_asks_and_names_the_task(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    from app.worker import automation_tick

    h = await auth_headers(client)
    task = (await client.post(f"{API}/tasks", json={"title": "Old invoice"}, headers=h)).json()
    wf = {
        "name": "Clean up",
        "trigger": {"type": "manual"},
        "steps": [
            {
                "kind": "tool",
                "name": "Delete it",
                "config": {"tool": "tasks_delete", "args": {"task_id": task["id"]}},
            }
        ],
    }
    wid = (await client.post(f"{API}/automations", json=wf, headers=h)).json()["id"]
    run = (await client.post(f"{API}/automations/{wid}/run", headers=h)).json()
    await automation_tick({})
    run = (await client.get(f"{API}/automation-runs/{run['id']}", headers=h)).json()
    assert run["status"] == "waiting_approval"
    assert run["steps"][0]["message"] == "Delete task “Old invoice”"
    assert (await client.get(f"{API}/tasks/{task['id']}", headers=h)).status_code == 200
    (row,) = await _audit("approval.requested")
    assert row.detail["tool"] == "tasks_delete"
