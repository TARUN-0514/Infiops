"""Phase 6b: detection, analytics, check-ins and monthly reports, from real data only."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select, update

from app.ai.gateway import ModelGateway, set_gateway
from app.ai.providers import ScriptedProvider
from app.ai.tools.builtin import get_registry
from app.ai.types import ModelUnavailableError
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Briefing, EmailMessage, Notification, Task, User
from app.services import checkins
from app.worker import briefing_tick
from tests.conftest import FakeGoogle, auth_headers, connect_google

API = "/api/v1"
IST = ZoneInfo("Asia/Kolkata")


def _local_at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, datetime.min.time(), IST).replace(hour=hour, minute=minute)


async def _event(
    client: AsyncClient, h: dict[str, str], title: str, start: datetime, mins: int
) -> None:
    r = await client.post(
        f"{API}/calendar/events",
        json={
            "title": title,
            "starts_at": start.astimezone(UTC).isoformat(),
            "ends_at": (start + timedelta(minutes=mins)).astimezone(UTC).isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 201, r.text


async def _task(client: AsyncClient, h: dict[str, str], title: str, **kw: Any) -> dict[str, Any]:
    r = await client.post(f"{API}/tasks", json={"title": title, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _quiet_schedule(client: AsyncClient, h: dict[str, str]) -> None:
    body = {"enabled": False, "midday": False, "evening": False, "monthly": False}
    assert (await client.put(f"{API}/briefings/settings", json=body, headers=h)).status_code == 200


# --- detection ----------------------------------------------------------------------


async def test_no_insights_without_data(client: AsyncClient) -> None:
    h = await auth_headers(client)
    r = await client.get(f"{API}/insights", headers=h)
    assert r.status_code == 200 and r.json()["insights"] == []
    assert r.json()["rules"]["reply_wait_hours"] == 48


async def test_insights_find_each_signal(client: AsyncClient, google: FakeGoogle) -> None:
    h = await auth_headers(client)
    now = datetime.now(UTC)
    await _task(client, h, "File taxes", due_at=(now - timedelta(days=2)).isoformat())
    pushed = await _task(client, h, "Clean garage")
    for _ in range(3):
        await client.post(f"{API}/tasks/{pushed['id']}/postpone", json={"days": 1}, headers=h)
    tomorrow = datetime.now(IST).date() + timedelta(days=1)
    await _event(client, h, "Design review", _local_at(tomorrow, 10), 60)
    await _event(client, h, "Vendor call", _local_at(tomorrow, 10, 30), 60)
    later = tomorrow + timedelta(days=1)
    for i in range(8):
        await _task(
            client, h, f"Report {i}", due_at=_local_at(later, 15).astimezone(UTC).isoformat()
        )
    account = await connect_google(client, h)
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        for pid, subject, age, prio in (
            ("m1", "Contract renewal", 3, "high"),
            ("m2", "Lunch?", 4, "normal"),
            ("m3", "Fresh question", 0, "high"),
        ):
            db.add(
                EmailMessage(
                    user_id=user.id,
                    account_id=account["id"],
                    provider_id=pid,
                    thread_id=pid,
                    from_name="Asha",
                    subject=subject,
                    received_at=now - timedelta(days=age, hours=1),
                    needs_reply=True,
                    priority=prio,
                )
            )
        await db.commit()

    found = {
        i["kind"]: i for i in (await client.get(f"{API}/insights", headers=h)).json()["insights"]
    }
    assert set(found) == {"overdue", "unanswered", "conflicts", "overloaded", "postponed"}
    assert [x["label"] for x in found["overdue"]["items"]] == ["File taxes"]
    # the fresh email is not flagged; the important one is listed first
    assert [x["label"] for x in found["unanswered"]["items"]] == ["Contract renewal", "Lunch?"]
    assert found["unanswered"]["severity"] == "high"
    assert found["conflicts"]["items"][0]["label"] == "Design review overlaps Vendor call"
    assert found["overloaded"]["items"][0]["id"] == later.isoformat()
    assert "8 tasks due" in found["overloaded"]["items"][0]["sub"]
    assert found["postponed"]["items"][0] == {
        "id": pushed["id"],
        "label": "Clean garage",
        "sub": "pushed back 3 times",
        "link": "/tasks",
    }


# --- analytics -------------------------------------------------------------------


async def test_analytics_empty_says_no_data(client: AsyncClient) -> None:
    h = await auth_headers(client)
    a = (await client.get(f"{API}/analytics?days=7", headers=h)).json()
    assert a["range"]["days"] == 7 and a["range"]["bucket"] == "day"
    assert len(a["tasks"]["series"]) >= 7
    assert a["tasks"]["completion_rate"] is None and a["tasks"]["on_time_rate"] is None
    assert a["time"]["categories"] == [] and a["habits"] == [] and a["goals"] == []
    assert a["finance"]["has_data"] is False and a["fitness"]["weight"] == []
    assert len(a["workload"]) == 14
    assert (await client.get(f"{API}/analytics?days=14", headers=h)).status_code == 422


async def test_analytics_from_logged_data(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = datetime.now(IST).date()
    soon = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    early = await _task(client, h, "Ship report", due_at=soon)
    late = await _task(
        client, h, "Pay rent", due_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()
    )
    await _task(client, h, "Still open")
    for t in (early, late):
        await client.post(f"{API}/tasks/{t['id']}/complete", headers=h)
    proj = (await client.post(f"{API}/projects", json={"name": "SOC2"}, headers=h)).json()
    await client.post(
        f"{API}/worklog",
        json={"content": "Evidence", "minutes": 120, "project_id": proj["id"]},
        headers=h,
    )
    habit = (
        await client.post(f"{API}/habits", json={"name": "Read", "per_week": 7}, headers=h)
    ).json()
    await client.put(
        f"{API}/habits/{habit['id']}/days", json={"day": today.isoformat(), "done": True}, headers=h
    )
    await client.post(
        f"{API}/goals",
        json={
            "title": "OSCP",
            "target_date": (today + timedelta(days=90)).isoformat(),
            "progress": 20,
        },
        headers=h,
    )
    await client.post(
        f"{API}/finance/transactions",
        json={
            "kind": "expense",
            "amount": "450.00",
            "occurred_on": today.isoformat(),
            "description": "Groceries",
            "category": "Food",
        },
        headers=h,
    )
    await client.post(
        f"{API}/fitness/workouts",
        json={
            "day": today.isoformat(),
            "minutes": 45,
            "sets": [{"exercise": "Push-up", "reps": 20}],
        },
        headers=h,
    )
    a = (await client.get(f"{API}/analytics?days=30", headers=h)).json()
    t = a["tasks"]
    assert t["created"] == 3 and t["completed"] == 2
    assert t["completion_rate"] == 67  # 2 of 3 created
    assert t["on_time_rate"] == 50 and t["with_due"] == 2  # rent was paid a day late
    assert sum(p["completed"] for p in t["series"]) == 2
    cats = {c["label"]: c["minutes"] for c in a["time"]["categories"]}
    assert cats == {"SOC2": 120, "Workouts": 45}
    assert a["habits"][0]["name"] == "Read" and a["habits"][0]["done"] == 1
    assert a["habits"][0]["streak"] == 1
    assert a["goals"][0]["progress"] == 20 and a["goals"][0]["behind"] is False
    assert a["finance"]["has_data"] and a["finance"]["top_categories"][0] == {
        "category": "Food",
        "spent": 450.0,
        "budget": None,
    }
    assert a["fitness"]["workouts"] == 1
    week = (await client.get(f"{API}/analytics?days=90", headers=h)).json()
    assert week["range"]["bucket"] == "week"


async def test_analytics_tool_never_goes_to_cloud() -> None:
    reg = get_registry()
    names = {s.name for s in reg.specs(cloud=True)}
    assert "insights_list" in names and "analytics_summary" not in names
    tool = reg.get("analytics_summary")
    assert tool is not None and tool.risk == "read"


# --- check-ins and monthly report -----------------------------------------------------------


async def test_midday_checkin_uses_real_facts(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    t = await _task(client, h, "Triage inbox")
    await client.post(f"{API}/tasks/{t['id']}/complete", headers=h)
    model.push("Good progress: one task done.")
    r = await client.post(f"{API}/checkins/midday", json={}, headers=h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["kind"] == "midday" and b["written_by_model"]
    assert b["data"]["done_so_far"] == ["Triage inbox"]
    assert "Never invent" in model.requests[0].system[0]["text"]
    today = (await client.get(f"{API}/checkins/today", headers=h)).json()
    assert today["midday"]["id"] == b["id"] and today["evening"] is None
    assert today["settings"]["midday_time"] == "13:00"
    hist = (await client.get(f"{API}/briefings?kind=midday", headers=h)).json()
    assert [x["id"] for x in hist] == [b["id"]]
    assert (await client.post(f"{API}/checkins/weekly", json={}, headers=h)).status_code == 422


async def test_evening_review_falls_back_offline(client: AsyncClient) -> None:
    h = await auth_headers(client)
    tomorrow = datetime.now(IST).date() + timedelta(days=1)
    await _event(client, h, "Standup", _local_at(tomorrow, 9, 30), 15)
    offline = ScriptedProvider("local")
    offline.push(ModelUnavailableError("offline"))
    set_gateway(ModelGateway(get_settings(), {"local": offline}))
    try:
        b = (await client.post(f"{API}/checkins/evening", json={}, headers=h)).json()
    finally:
        set_gateway(None)
    assert b["written_by_model"] is False
    assert b["content"].startswith("Evening review, Owner.")
    assert "09:30-09:45 Standup" in b["content"]
    assert b["data"]["tomorrow"]["events"][0]["title"] == "Standup"


async def test_monthly_report_stays_local(
    client: AsyncClient, cloud: tuple[ScriptedProvider, ScriptedProvider]
) -> None:
    local, remote = cloud
    h = await auth_headers(client)
    today = datetime.now(IST).date()
    await client.post(
        f"{API}/finance/transactions",
        json={
            "kind": "income",
            "amount": "1000.00",
            "occurred_on": today.isoformat(),
            "description": "Salary",
        },
        headers=h,
    )
    local.push("## November in review\nIncome 1,000.")
    month = f"{today.year}-{today.month:02d}"
    r = await client.post(f"{API}/reports/monthly", json={"month": month}, headers=h)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["kind"] == "monthly" and rep["for_date"] == today.replace(day=1).isoformat()
    assert rep["data"]["money"]["income"] == 1000.0
    assert len(local.requests) == 1 and remote.requests == []
    assert [x["id"] for x in (await client.get(f"{API}/reports/monthly", headers=h)).json()] == [
        rep["id"]
    ]
    nxt = (today.replace(day=28) + timedelta(days=5)).replace(day=1)
    r = await client.post(
        f"{API}/reports/monthly", json={"month": f"{nxt.year}-{nxt.month:02d}"}, headers=h
    )
    assert r.status_code == 400
    assert (
        await client.post(f"{API}/reports/monthly", json={"month": "2026-13"}, headers=h)
    ).status_code == 422


async def test_scheduled_midday_checkin_notifies_once(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    await _quiet_schedule(client, h)
    local = datetime.now(IST)
    hhmm = (
        "00:00"
        if local.hour == 0 and local.minute < 5
        else (local - timedelta(minutes=5)).strftime("%H:%M")
    )
    r = await client.put(
        f"{API}/briefings/settings", json={"midday": True, "midday_time": hhmm}, headers=h
    )
    assert r.json()["midday_time"] == hhmm
    model.push("Halfway there.")
    assert await briefing_tick({}) == 1
    assert await briefing_tick({}) == 0
    async with get_sessionmaker()() as db:
        n = await db.scalar(select(Notification))
        assert n is not None and n.link == "/briefing?tab=midday"
        assert [b.kind for b in await db.scalars(select(Briefing))] == ["midday"]


async def test_monthly_report_due_on_first_days(client: AsyncClient) -> None:
    h = await auth_headers(client)
    await client.put(
        f"{API}/briefings/settings", json={"midday": False, "evening": False}, headers=h
    )
    async with get_sessionmaker()() as db:
        at = datetime(2026, 12, 2, 9, 0, tzinfo=IST).astimezone(UTC)
        due = [(k, d) for _, k, d in await checkins.due(db, now=at)]
        assert due == [("monthly", date(2026, 11, 1))]
        before_morning = datetime(2026, 12, 1, 6, 0, tzinfo=IST).astimezone(UTC)
        assert await checkins.due(db, now=before_morning) == []
        assert await checkins.due(db, now=datetime(2026, 12, 9, 9, 0, tzinfo=IST)) == []


async def test_postponed_count_drives_task_analytics(client: AsyncClient) -> None:
    h = await auth_headers(client)
    t = await _task(client, h, "Write blog")
    async with get_sessionmaker()() as db:
        await db.execute(update(Task).values(postponed_count=4))
        await db.commit()
    a = (await client.get(f"{API}/analytics?days=7", headers=h)).json()
    assert a["tasks"]["postponed"] == [{"id": t["id"], "title": "Write blog", "times": 4}]
