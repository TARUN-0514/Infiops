"""Personal life: goals, routines, lists, journal (encrypted) and important dates."""

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, text

from app.ai.providers import ScriptedProvider
from app.ai.timeutil import now_local
from app.db.session import get_sessionmaker
from app.models import JournalEntry, Notification, User
from app.services import personal
from tests.conftest import auth_headers
from tests.test_chat import _conv, _send

API = "/api/v1"


def _today() -> date:
    return now_local("Asia/Kolkata").date()


async def test_goals_progress_from_milestones(client: AsyncClient) -> None:
    h = await auth_headers(client)
    target = _today() + timedelta(days=60)
    r = await client.post(
        f"{API}/goals",
        json={
            "title": "Pass OSCP",
            "area": "career",
            "target_date": target.isoformat(),
            "milestones": [{"title": "Finish course"}, {"title": "30 labs", "done": True}],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["progress"] == 50 and g["days_left"] == 60
    r = await client.put(
        f"{API}/goals/{g['id']}",
        json={
            "title": "Pass OSCP",
            "progress": 10,
            "milestones": [
                {"title": "Finish course", "done": True},
                {"title": "30 labs", "done": True},
            ],
        },
        headers=h,
    )
    assert r.json()["progress"] == 100
    r = await client.post(f"{API}/goals", json={"title": "Read", "progress": 30}, headers=h)
    assert r.json()["progress"] == 30
    assert (
        await client.post(f"{API}/goals", json={"title": "x", "progress": 101}, headers=h)
    ).status_code == 422
    assert len((await client.get(f"{API}/goals", headers=h)).json()) == 2


async def test_routines_steps_and_streak(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = _today()
    r = await client.post(
        f"{API}/routines",
        json={"name": "Morning", "time_of_day": "morning", "steps": ["Water", "Stretch", "Plan"]},
        headers=h,
    )
    rid = r.json()["id"]
    r = await client.put(
        f"{API}/routines/{rid}/log",
        json={"day": today.isoformat(), "done_steps": [0, 1, 2, 9, 1]},
        headers=h,
    )
    assert r.json()["done_steps"] == [0, 1, 2]
    await client.put(
        f"{API}/routines/{rid}/log",
        json={"day": (today - timedelta(days=1)).isoformat(), "done_steps": [0]},
        headers=h,
    )
    got = (await client.get(f"{API}/routines", params={"days": 7}, headers=h)).json()["routines"][0]
    assert got["due_today"] and got["done_steps"] == [0, 1, 2]
    assert got["completed_days"] == 1 and got["due_days"] == 7
    future = await client.put(
        f"{API}/routines/{rid}/log",
        json={"day": (today + timedelta(days=1)).isoformat(), "done_steps": [0]},
        headers=h,
    )
    assert future.status_code == 400
    await client.put(
        f"{API}/routines/{rid}/log", json={"day": today.isoformat(), "done_steps": []}, headers=h
    )
    got = (await client.get(f"{API}/routines", headers=h)).json()["routines"][0]
    assert got["done_steps"] == []

    other_day = (today.weekday() + 1) % 7
    r = await client.post(
        f"{API}/routines", json={"name": "Gym", "steps": ["Go"], "weekdays": [other_day]}, headers=h
    )
    rows = (await client.get(f"{API}/routines", params={"days": 7}, headers=h)).json()["routines"]
    gym = next(x for x in rows if x["name"] == "Gym")
    assert not gym["due_today"] and gym["due_days"] == 1


async def test_lists_and_items(client: AsyncClient) -> None:
    h = await auth_headers(client)
    lid = (
        await client.post(f"{API}/lists", json={"name": "Groceries", "kind": "shopping"}, headers=h)
    ).json()["id"]
    a = (await client.post(f"{API}/lists/{lid}/items", json={"text": "Milk"}, headers=h)).json()
    await client.post(f"{API}/lists/{lid}/items", json={"text": "Eggs"}, headers=h)
    r = await client.patch(f"{API}/list-items/{a['id']}", json={"done": True}, headers=h)
    assert r.json()["done"] is True
    lists = (await client.get(f"{API}/lists", headers=h)).json()
    assert [i["text"] for i in lists[0]["items"]] == ["Eggs", "Milk"]  # done items sink
    assert (
        await client.post(f"{API}/lists/{lid}/items", json={"text": ""}, headers=h)
    ).status_code == 422
    assert (await client.delete(f"{API}/list-items/{a['id']}", headers=h)).status_code == 204


async def test_journal_encrypted_and_searchable(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = _today()
    r = await client.post(
        f"{API}/journal",
        json={
            "day": today.isoformat(),
            "mood": 4,
            "content": "Rooted Kevin today, felt great",
            "tags": ["oscp"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    await client.post(
        f"{API}/journal", json={"day": today.isoformat(), "mood": 2, "content": "Tired"}, headers=h
    )
    j = (await client.get(f"{API}/journal", headers=h)).json()
    assert len(j["entries"]) == 2 and j["days_written"] == 1 and j["average_mood"] == 3.0
    found = (await client.get(f"{API}/journal", params={"q": "kevin"}, headers=h)).json()
    assert len(found["entries"]) == 1
    tagged = (await client.get(f"{API}/journal", params={"tag": "oscp"}, headers=h)).json()
    assert len(tagged["entries"]) == 1
    async with get_sessionmaker()() as db:
        raw = (await db.execute(text("SELECT content FROM journal_entries"))).scalars().all()
    assert all(isinstance(x, bytes) and b"Kevin" not in x for x in raw)
    future = await client.post(
        f"{API}/journal",
        json={"day": (today + timedelta(days=1)).isoformat(), "content": "x"},
        headers=h,
    )
    assert future.status_code == 400
    assert (
        await client.get(f"{API}/journal", params={"month": "2026-13"}, headers=h)
    ).status_code == 400


def _d(**kw: Any) -> Any:
    base = {"month": 1, "day": 1, "year": None, "yearly": True}
    return SimpleNamespace(**{**base, **kw})


def test_next_occurrence_and_leap_day() -> None:
    today = date(2027, 3, 10)
    assert personal.next_occurrence(_d(month=3, day=10), today) == today
    assert personal.next_occurrence(_d(month=3, day=9), today) == date(2028, 3, 9)
    assert personal.next_occurrence(_d(month=2, day=29), date(2027, 1, 1)) == date(2027, 2, 28)
    assert personal.next_occurrence(_d(month=2, day=29), date(2027, 3, 1)) == date(2028, 2, 29)
    one_off = _d(month=1, day=5, year=2027, yearly=False)
    assert personal.next_occurrence(one_off, today) is None  # long past
    assert personal.next_occurrence(_d(month=4, day=1, year=None, yearly=False), today) is None


async def test_important_dates_and_reminders_once(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = _today()
    soon = today + timedelta(days=2)
    r = await client.post(
        f"{API}/important-dates",
        json={
            "title": "Amma's birthday",
            "month": soon.month,
            "day": soon.day,
            "year": soon.year - 60,
            "remind_days": 3,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["days_left"] == 2 and r.json()["turning"] == 60
    far = today + timedelta(days=40)
    await client.post(
        f"{API}/important-dates",
        json={"title": "Car insurance", "kind": "renewal", "month": far.month, "day": far.day},
        headers=h,
    )
    bad = await client.post(
        f"{API}/important-dates", json={"title": "x", "month": 2, "day": 30}, headers=h
    )
    assert bad.status_code == 400
    bad = await client.post(
        f"{API}/important-dates",
        json={"title": "x", "month": 2, "day": 3, "yearly": False},
        headers=h,
    )
    assert bad.status_code == 400
    listed = (await client.get(f"{API}/important-dates", headers=h)).json()
    assert [x["title"] for x in listed] == ["Amma's birthday", "Car insurance"]

    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        assert await personal.date_reminders(db, user, today) == 1
        await db.commit()
        assert await personal.date_reminders(db, user, today) == 0
        assert await personal.date_reminders(db, user, today + timedelta(days=1)) == 0
        await db.commit()
        n = await db.scalar(select(Notification).where(Notification.kind == "date"))
    assert n is not None and "turning 60" in n.title and n.link == "/personal?tab=dates"


async def test_personal_isolation(client: AsyncClient) -> None:
    h = await auth_headers(client)
    async with get_sessionmaker()() as db:
        other = User(email="x@example.com", password_hash="x", display_name="X")
        db.add(other)
        await db.flush()
        e = JournalEntry(user_id=other.id, day=_today(), content="theirs", tags=[])
        db.add(e)
        await db.commit()
    assert (await client.get(f"{API}/journal", headers=h)).json()["entries"] == []
    assert (await client.delete(f"{API}/journal/{e.id}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/goals")).status_code == 401


async def test_journal_tool_is_local_only(
    client: AsyncClient, cloud: tuple[ScriptedProvider, ScriptedProvider]
) -> None:
    local, remote = cloud
    h = await auth_headers(client)
    cid = await _conv(client, h)
    remote.push("ok")
    await _send(client, h, cid, "hi", cloud=True)
    names = {t.name for t in remote.requests[0].tools}
    assert "journal_add" not in names and "workspace_find" in names

    lid = (await client.post(f"{API}/lists", json={"name": "Reading"}, headers=h)).json()["id"]
    local.push(
        [
            {"name": "list_add", "input": {"list_name": "reading", "items": ["Dune", "Hyperion"]}},
            {"name": "journal_add", "input": {"content": "Good day", "mood": 4}},
        ],
        "Done.",
    )
    events = await _send(client, h, cid, "add dune and hyperion to reading, and journal: good day")
    done = [e for e in events if e["type"] == "tool.finished"]
    assert all(d["status"] == "succeeded" for d in done), done
    lists = (await client.get(f"{API}/lists", headers=h)).json()
    assert next(x for x in lists if x["id"] == lid)["items"][0]["text"] == "Dune"
    assert (await client.get(f"{API}/journal", headers=h)).json()["entries"][0]["mood"] == 4
