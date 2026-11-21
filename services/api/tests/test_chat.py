import json
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.providers import ScriptedProvider
from app.db.session import get_sessionmaker
from app.models import MemoryItem, Task, ToolExecution
from app.services import memory as mem
from tests.conftest import auth_headers

API = "/api/v1"


async def _send(
    client: AsyncClient, h: dict[str, str], cid: str, text: str, **extra: Any
) -> list[dict[str, Any]]:
    r = await client.post(
        f"{API}/chat/conversations/{cid}/messages", json={"text": text, **extra}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in r.text.splitlines() if line]


async def _conv(client: AsyncClient, h: dict[str, str]) -> str:
    r = await client.post(f"{API}/chat/conversations", headers=h)
    assert r.status_code == 201
    return str(r.json()["id"])


async def test_plain_reply_streams_and_is_saved(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    cid = await _conv(client, h)
    model.push("Hello Tarun, how can I help?")
    events = await _send(client, h, cid, "Hi there")
    types = [e["type"] for e in events]
    assert types[0] == "run.started" and types[-1] == "run.finished"
    assert "text.delta" in types and "message.completed" in types
    assert events[0]["provider"] == "local"
    done = next(e for e in events if e["type"] == "message.completed")
    assert done["message"]["text"] == "Hello Tarun, how can I help?"

    conv = (await client.get(f"{API}/chat/conversations/{cid}", headers=h)).json()
    assert conv["conversation"]["title"] == "Hi there"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    # system prompt carries the current local time and treats memory as data
    system = model.requests[0].system
    assert "Current local time" in system[1]["text"] and "<memories>" in system[1]["text"]


async def test_tool_call_creates_task(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    cid = await _conv(client, h)
    model.push(
        [
            {
                "name": "tasks_create",
                "input": {
                    "title": "Pay rent",
                    "due_date": "2026-12-01",
                    "recurrence": "FREQ=MONTHLY;BYMONTHDAY=1",
                    "project": "Home",
                },
            }
        ],
        "Done. Rent is on your list for the 1st of every month.",
    )
    events = await _send(client, h, cid, "remind me to pay rent on the 1st every month")
    finished = next(e for e in events if e["type"] == "tool.finished")
    assert finished["status"] == "succeeded"
    async with get_sessionmaker()() as db:
        task = (await db.scalars(select(Task))).one()
    assert task.title == "Pay rent" and task.recurrence == "FREQ=MONTHLY;BYMONTHDAY=1"
    assert task.source == "assistant" and task.project_id is not None
    # second model call saw the tool result
    last = model.requests[-1].messages[-1]
    assert last["content"][0]["type"] == "tool_result"


async def test_invalid_tool_input_is_returned_to_model_not_run(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    cid = await _conv(client, h)
    model.push([{"name": "tasks_create", "input": {"bogus": 1}}], "Sorry, let me retry.")
    events = await _send(client, h, cid, "add a task")
    finished = next(e for e in events if e["type"] == "tool.finished")
    assert finished["status"] == "failed"
    result = model.requests[-1].messages[-1]["content"][0]
    assert result["is_error"] is True


async def test_sensitive_tool_waits_for_approval_then_runs(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    r = await client.post(f"{API}/tasks", json={"title": "Old task"}, headers=h)
    task_id = r.json()["id"]
    cid = await _conv(client, h)
    model.push([{"name": "tasks_delete", "input": {"task_id": task_id}}])
    events = await _send(client, h, cid, "delete my old task")
    approval = next(e for e in events if e["type"] == "approval.required")["approval"]
    assert approval["risk"] == "sensitive"
    assert events[-1] == {
        "type": "run.finished",
        "run_id": approval["run_id"],
        "status": "waiting_approval",
    }
    # not deleted yet
    assert (await client.get(f"{API}/tasks/{task_id}", headers=h)).status_code == 200
    pending = (await client.get(f"{API}/approvals?status=pending", headers=h)).json()
    assert [p["id"] for p in pending] == [approval["id"]]
    assert pending[0]["conversation_id"] == cid

    model.push("Deleted it.")
    r = await client.post(
        f"{API}/approvals/{approval['id']}/decide", json={"approve": True}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["status"] == "approved"
    assert r.json()["message"]["text"] == "Deleted it."
    assert (await client.get(f"{API}/tasks/{task_id}", headers=h)).status_code == 404
    again = await client.post(
        f"{API}/approvals/{approval['id']}/decide", json={"approve": True}, headers=h
    )
    assert again.status_code == 400


async def test_rejected_approval_tells_the_model(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    task_id = (await client.post(f"{API}/tasks", json={"title": "Keep"}, headers=h)).json()["id"]
    cid = await _conv(client, h)
    model.push([{"name": "tasks_delete", "input": {"task_id": task_id}}])
    events = await _send(client, h, cid, "delete it")
    approval = next(e for e in events if e["type"] == "approval.required")["approval"]
    model.push("Okay, I left it.")
    r = await client.post(
        f"{API}/approvals/{approval['id']}/decide", json={"approve": False}, headers=h
    )
    assert r.json()["approval"]["status"] == "rejected"
    assert (await client.get(f"{API}/tasks/{task_id}", headers=h)).status_code == 200
    result = model.requests[-1].messages[-1]["content"][0]
    assert result["is_error"] and "declined" in result["content"]


async def test_denied_policy_blocks_without_asking(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    await client.put(f"{API}/tools/tasks_create/permission", json={"decision": "deny"}, headers=h)
    cid = await _conv(client, h)
    model.push([{"name": "tasks_create", "input": {"title": "x"}}], "I can't add tasks.")
    events = await _send(client, h, cid, "add x")
    assert next(e for e in events if e["type"] == "tool.finished")["status"] == "denied"
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(Task))).first() is None
        exe = (await db.scalars(select(ToolExecution))).one()
    assert exe.status == "denied"


async def test_moving_on_expires_pending_approval(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    task_id = (await client.post(f"{API}/tasks", json={"title": "T"}, headers=h)).json()["id"]
    cid = await _conv(client, h)
    model.push([{"name": "tasks_delete", "input": {"task_id": task_id}}])
    events = await _send(client, h, cid, "delete T")
    approval = next(e for e in events if e["type"] == "approval.required")["approval"]
    model.push("Sure, what next?")
    await _send(client, h, cid, "never mind")
    listed = (await client.get(f"{API}/approvals", headers=h)).json()
    assert listed[0]["id"] == approval["id"] and listed[0]["status"] == "expired"
    # history sent to the model stays valid: tool_use is answered before the new text
    msgs = model.requests[-1].messages
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "user", "user"]
    assert msgs[2]["content"][0]["type"] == "tool_result"


async def test_memory_is_used_and_cited(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    async with get_sessionmaker()() as db:
        await mem.remember(
            db, me["id"], "The user prefers black coffee with no sugar", category="preference"
        )
        await db.commit()
    cid = await _conv(client, h)
    model.push("Black coffee, no sugar, as you like it.")
    events = await _send(client, h, cid, "how do I take my coffee?")
    used = next(e for e in events if e["type"] == "memory.used")
    assert "black coffee" in used["sources"][0]["content"]
    assert "black coffee" in model.requests[0].system[1]["text"]
    done = next(e for e in events if e["type"] == "message.completed")
    assert done["message"]["sources"][0]["type"] == "memory"
    async with get_sessionmaker()() as db:
        item = (await db.scalars(select(MemoryItem))).one()
    assert item.last_used_at is not None


async def test_offline_model_gives_honest_message(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    import httpx

    h = await auth_headers(client)
    cid = await _conv(client, h)
    model.push(httpx.ConnectError("refused"))
    events = await _send(client, h, cid, "hello")
    err = next(e for e in events if e["type"] == "error")
    assert err["code"] == "no_provider" and "Ollama" in err["message"]
    assert events[-1]["status"] == "failed"


async def test_cloud_request_refused_when_cloud_off(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    cid = await _conv(client, h)
    events = await _send(client, h, cid, "hard question", cloud=True)
    err = next(e for e in events if e["type"] == "error")
    assert "Cloud is off" in err["message"]


async def test_search_and_isolation(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    cid = await _conv(client, h)
    model.push("Your passport renewal is noted.")
    await _send(client, h, cid, "remind me about the passport renewal")
    hits = (await client.get(f"{API}/chat/search?q=passport", headers=h)).json()
    assert hits and all(x["conversation_id"] == cid for x in hits)
    assert (
        await client.get(
            f"{API}/chat/conversations/00000000-0000-0000-0000-000000000000", headers=h
        )
    ).status_code == 404
