from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.gateway import ModelGateway, set_gateway
from app.ai.providers import ScriptedProvider
from app.ai.types import ModelUnavailableError
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Briefing, Notification, User
from app.services import briefing as svc
from app.services import notify
from app.worker import briefing_tick
from tests.conftest import auth_headers

API = "/api/v1"
IST = ZoneInfo("Asia/Kolkata")


async def test_work_log_and_completed_tasks(client: AsyncClient) -> None:
    h = await auth_headers(client)
    r = await client.post(
        f"{API}/worklog", json={"content": "Triaged 14 scanner findings", "minutes": 90}, headers=h
    )
    assert r.status_code == 201 and r.json()["source"] == "manual"
    task = (await client.post(f"{API}/tasks", json={"title": "Patch nginx"}, headers=h)).json()
    await client.post(f"{API}/tasks/{task['id']}/complete", headers=h)
    entries = (await client.get(f"{API}/worklog", headers=h)).json()
    assert {e["content"] for e in entries} == {
        "Triaged 14 scanner findings",
        "Completed: Patch nginx",
    }
    auto = next(e for e in entries if e["source"] == "task")
    assert auto["task_id"] == task["id"]
    lid = entries[0]["id"]
    r = await client.patch(f"{API}/worklog/{lid}", json={"minutes": 30}, headers=h)
    assert r.json()["minutes"] == 30
    assert (await client.delete(f"{API}/worklog/{lid}", headers=h)).status_code == 204


async def test_weekly_report_uses_only_logged_facts(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    await client.post(f"{API}/worklog", json={"content": "Finished SOC2 evidence pack"}, headers=h)
    model.push("## Summary\nFinished the SOC2 evidence pack.")
    r = await client.post(f"{API}/reports", json={}, headers=h)
    assert r.status_code == 201
    report = r.json()
    assert report["kind"] == "weekly_status" and report["written_by_model"]
    assert report["data"]["work_log"][0]["entry"] == "Finished SOC2 evidence pack"
    assert "<facts>" in model.requests[0].messages[0]["content"]
    assert "Never invent" in model.requests[0].system[0]["text"]
    assert len((await client.get(f"{API}/reports", headers=h)).json()) == 1


async def test_empty_week_report_is_written_without_model(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    report = (await client.post(f"{API}/reports", json={}, headers=h)).json()
    assert report["written_by_model"] is False and "Nothing logged" in report["content"]
    assert model.requests == []


async def test_morning_briefing_from_real_data(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    today = datetime.now(IST).date()
    await client.post(
        f"{API}/tasks",
        json={
            "title": "Renew passport",
            "due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
        headers=h,
    )
    start = datetime.combine(today, datetime.min.time(), IST).replace(hour=15).astimezone(UTC)
    await client.post(
        f"{API}/calendar/events",
        json={
            "title": "1:1 with Asha",
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
        },
        headers=h,
    )
    model.push("Good morning! One meeting and an overdue passport renewal.")
    r = await client.post(f"{API}/briefings/today", json={}, headers=h)
    b = r.json()
    assert b["for_date"] == today.isoformat() and b["written_by_model"]
    assert b["data"]["tasks"][0] == {"title": "Renew passport", "priority": "none", "overdue": True}
    assert b["data"]["events"][0]["title"] == "1:1 with Asha"
    # asking again returns the same briefing without another model call
    again = (await client.post(f"{API}/briefings/today", json={}, headers=h)).json()
    assert again["id"] == b["id"] and len(model.requests) == 1
    got = (await client.get(f"{API}/briefings/today", headers=h)).json()
    assert got["briefing"]["id"] == b["id"] and got["settings"]["time"] == "07:30"


async def test_briefing_falls_back_when_model_is_offline(client: AsyncClient) -> None:
    h = await auth_headers(client)
    offline = ScriptedProvider("local")
    offline.push(ModelUnavailableError("Can't reach the local model."))
    set_gateway(ModelGateway(get_settings(), {"local": offline}))
    try:
        b = (await client.post(f"{API}/briefings/today", json={}, headers=h)).json()
    finally:
        set_gateway(None)
    assert b["written_by_model"] is False
    assert b["content"].startswith("Good morning, Owner.") and "No events" in b["content"]


async def test_scheduled_briefing_notifies_once(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    now_local = datetime.now(IST)
    hhmm = (now_local - timedelta(minutes=5)).strftime("%H:%M")
    if now_local.hour == 0 and now_local.minute < 5:
        hhmm = "00:00"
    r = await client.put(f"{API}/briefings/settings", json={"time": hhmm}, headers=h)
    assert r.json()["time"] == hhmm
    model.push("Morning! Quiet day.")
    assert await briefing_tick({}) == 1
    assert await briefing_tick({}) == 0  # already delivered today
    notes = (await client.get(f"{API}/notifications", headers=h)).json()
    assert notes["unread"] == 1 and notes["items"][0]["link"] == "/briefing"
    await client.post(f"{API}/notifications/read-all", headers=h)
    assert (await client.get(f"{API}/notifications", headers=h)).json()["unread"] == 0
    async with get_sessionmaker()() as db:
        assert len(list(await db.scalars(select(Briefing)))) == 1
        assert (await db.scalar(select(Notification))).pushed is False  # type: ignore[union-attr]


async def test_briefing_not_due_outside_window() -> None:
    async with get_sessionmaker()() as db:
        db.add(
            User(
                email="a@example.com", password_hash="x", display_name="A", timezone="Asia/Kolkata"
            )
        )
        await db.commit()
        noon = datetime(2026, 11, 21, 6, 30, tzinfo=UTC)  # 12:00 IST
        assert await svc.due_users(db, now=noon) == []
        early = datetime(2026, 11, 21, 2, 30, tzinfo=UTC)  # 08:00 IST
        assert len(await svc.due_users(db, now=early)) == 1


async def test_push_subscription_and_keys(client: AsyncClient) -> None:
    h = await auth_headers(client)
    key = (await client.get(f"{API}/push/key", headers=h)).json()["public_key"]
    assert len(key) > 80 and key == notify.vapid_keys()[0]
    sub = {"endpoint": "https://push.example.com/abc", "p256dh": "B" * 87, "auth": "a" * 22}
    assert (await client.post(f"{API}/push/subscriptions", json=sub, headers=h)).status_code == 201
    bad = {**sub, "endpoint": "http://insecure.example"}
    assert (await client.post(f"{API}/push/subscriptions", json=bad, headers=h)).status_code == 422
    r = await client.post(f"{API}/push/unsubscribe", json={"endpoint": sub["endpoint"]}, headers=h)
    assert r.json() == {"ok": True}
