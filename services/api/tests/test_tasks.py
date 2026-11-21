from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.ai.providers import ScriptedProvider
from tests.conftest import auth_headers

API = "/api/v1"


async def test_crud_subtasks_and_projects(client: AsyncClient) -> None:
    h = await auth_headers(client)
    p = (await client.post(f"{API}/projects", json={"name": "OSCP prep"}, headers=h)).json()
    assert (
        await client.post(f"{API}/projects", json={"name": "oscp PREP"}, headers=h)
    ).status_code == 400
    r = await client.post(
        f"{API}/tasks",
        json={
            "title": "Finish AD labs",
            "project_id": p["id"],
            "priority": "high",
            "subtasks": ["Kerberoasting", "DCSync"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["subtasks_total"] == 2
    detail = (await client.get(f"{API}/tasks/{task['id']}", headers=h)).json()
    sub = detail["subtasks"][0]
    await client.patch(f"{API}/tasks/{sub['id']}", json={"status": "done"}, headers=h)
    top = (await client.get(f"{API}/tasks", headers=h)).json()
    assert len(top) == 1 and top[0]["subtasks_done"] == 1
    projects = (await client.get(f"{API}/projects", headers=h)).json()
    assert projects[0]["open_tasks"] == 1
    # no sub-subtasks
    bad = await client.post(
        f"{API}/tasks", json={"title": "x", "parent_task_id": sub["id"]}, headers=h
    )
    assert bad.status_code == 400
    assert (await client.delete(f"{API}/tasks/{task['id']}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/tasks", headers=h)).json() == []


async def test_recurring_task_rolls_forward(client: AsyncClient) -> None:
    h = await auth_headers(client)
    due = "2026-12-01T09:00:00+05:30"
    t = (
        await client.post(
            f"{API}/tasks",
            json={"title": "Pay rent", "due_at": due, "recurrence": "FREQ=MONTHLY;BYMONTHDAY=1"},
            headers=h,
        )
    ).json()
    r = (await client.post(f"{API}/tasks/{t['id']}/complete", headers=h)).json()
    assert r["task"]["status"] == "done"
    nxt = datetime.fromisoformat(r["next"]["due_at"])
    assert nxt == datetime(2027, 1, 1, 3, 30, tzinfo=UTC)
    bad = await client.post(
        f"{API}/tasks", json={"title": "x", "recurrence": "FREQ=NOPE"}, headers=h
    )
    assert bad.status_code == 400
    norule = await client.post(
        f"{API}/tasks", json={"title": "x", "recurrence": "FREQ=DAILY"}, headers=h
    )
    assert norule.status_code == 400  # repeating needs a due date


async def test_postpone_and_today(client: AsyncClient) -> None:
    h = await auth_headers(client)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    t = (
        await client.post(f"{API}/tasks", json={"title": "Late", "due_at": yesterday}, headers=h)
    ).json()
    today = (await client.get(f"{API}/tasks/today", headers=h)).json()
    assert [x["title"] for x in today["overdue"]] == ["Late"]
    r = (await client.post(f"{API}/tasks/{t['id']}/postpone", json={"days": 2}, headers=h)).json()
    assert r["postponed_count"] == 1


async def test_parse_preview(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    model.push(
        {
            "title": "Call mom",
            "notes": "",
            "due_date": "2026-11-22",
            "due_time": "18:00",
            "priority": "none",
            "project": "",
            "recurrence": "",
            "subtasks": [],
        }
    )
    r = await client.post(
        f"{API}/tasks/parse", json={"text": "call mom tomorrow evening"}, headers=h
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Call mom" and body["all_day"] is False
    assert body["due_at"] == "2026-11-22T12:30:00+00:00"  # 18:00 Asia/Kolkata
    req = model.requests[0]
    assert req.json_schema is not None and "Current local time" in req.system[1]["text"]
    model.push(
        {
            "title": "",
            "notes": "",
            "due_date": "",
            "due_time": "",
            "priority": "none",
            "project": "",
            "recurrence": "",
            "subtasks": [],
        }
    )
    r = await client.post(f"{API}/tasks/parse", json={"text": "asdf"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "unparseable"


async def test_upload_validation(client: AsyncClient) -> None:
    h = await auth_headers(client)
    ok = await client.post(
        f"{API}/uploads", files={"file": ("n.txt", b"hello", "text/plain")}, headers=h
    )
    assert ok.status_code == 201
    fake = await client.post(
        f"{API}/uploads", files={"file": ("x.png", b"not a png", "image/png")}, headers=h
    )
    assert fake.status_code == 400
    exe = await client.post(
        f"{API}/uploads", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=h
    )
    assert exe.status_code == 400
