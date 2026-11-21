from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient

from app.ai.providers import ScriptedProvider
from app.models import CalendarEvent
from app.services import calendar as cal
from tests.conftest import auth_headers, connect_google
from tests.fake_google import FakeGoogle

API = "/api/v1"
IST = ZoneInfo("Asia/Kolkata")


def _at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), IST).astimezone(UTC)


def _ev(start: datetime, minutes: int, all_day: bool = False) -> CalendarEvent:
    return CalendarEvent(
        title="x",
        starts_at=start,
        ends_at=start + timedelta(minutes=minutes),
        all_day=all_day,
        attendees=[],
    )


def test_free_slots_and_conflicts() -> None:
    day = date(2026, 11, 23)
    events = [_ev(_at(day, 10), 60), _ev(_at(day, 10, 30), 60), _ev(_at(day, 14), 30)]
    events.append(_ev(_at(day, 0), 24 * 60, all_day=True))  # all-day doesn't block time
    slots = cal.free_slots(events, day, "Asia/Kolkata", minutes=30, now=_at(day, 6))
    got = [
        (s.start.astimezone(IST).strftime("%H:%M"), s.end.astimezone(IST).strftime("%H:%M"))
        for s in slots
    ]
    assert got == [("09:00", "10:00"), ("11:30", "14:00"), ("14:30", "18:00")]
    assert len(cal.find_conflicts(events)) == 1
    # later in the day, past time isn't offered
    later = cal.free_slots(events, day, "Asia/Kolkata", minutes=30, now=_at(day, 15))
    assert later[0].start == _at(day, 15)


async def test_local_events_without_google(client: AsyncClient) -> None:
    h = await auth_headers(client)
    day = datetime.now(IST).date() + timedelta(days=1)
    r = await client.post(
        f"{API}/calendar/events",
        json={
            "title": "Dentist",
            "starts_at": _at(day, 11).isoformat(),
            "ends_at": _at(day, 12).isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["google"] is False and ev["source"] == "local"
    r = await client.post(
        f"{API}/calendar/events",
        json={
            "title": "Bad",
            "starts_at": _at(day, 12).isoformat(),
            "ends_at": _at(day, 11).isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 400
    rng = {"start": _at(day, 0).isoformat(), "end": _at(day + timedelta(days=1), 0).isoformat()}
    listing = (await client.get(f"{API}/calendar/events", params=rng, headers=h)).json()
    assert [e["title"] for e in listing["events"]] == ["Dentist"]
    assert listing["google_connected"] is False
    r = await client.patch(
        f"{API}/calendar/events/{ev['id']}", json={"title": "Dentist (moved)"}, headers=h
    )
    assert r.json()["title"] == "Dentist (moved)"
    slots = (
        await client.get(
            f"{API}/calendar/free-slots", params={"day": day.isoformat(), "minutes": 60}, headers=h
        )
    ).json()
    assert all(
        not (s["start"] < _at(day, 12).isoformat() and s["end"] > _at(day, 11).isoformat())
        for s in slots
    )
    assert (await client.delete(f"{API}/calendar/events/{ev['id']}", headers=h)).status_code == 204


async def test_google_events_sync_and_write_back(client: AsyncClient, google: FakeGoogle) -> None:
    h = await auth_headers(client)
    await connect_google(client, h)
    start = datetime.now(UTC) + timedelta(days=1)
    google.add_event("Design review", start, 45)
    await client.post(f"{API}/email/sync", headers=h)
    rng = {
        "start": (start - timedelta(hours=1)).isoformat(),
        "end": (start + timedelta(hours=2)).isoformat(),
    }
    events = (await client.get(f"{API}/calendar/events", params=rng, headers=h)).json()["events"]
    assert [e["title"] for e in events] == ["Design review"] and events[0]["google"]

    # events made in NEXUS go to Google too
    r = await client.post(
        f"{API}/calendar/events",
        json={
            "title": "Lunch",
            "starts_at": (start + timedelta(hours=3)).isoformat(),
            "ends_at": (start + timedelta(hours=4)).isoformat(),
        },
        headers=h,
    )
    assert r.json()["google"] is True
    assert any(e.get("summary") == "Lunch" for e in google.events.values())
    eid = r.json()["id"]
    await client.patch(f"{API}/calendar/events/{eid}", json={"title": "Team lunch"}, headers=h)
    assert any(e.get("summary") == "Team lunch" for e in google.events.values())
    await client.delete(f"{API}/calendar/events/{eid}", headers=h)
    assert not any(e.get("summary") == "Team lunch" for e in google.events.values())

    # an event cancelled in Google disappears after the next sync
    gid = next(k for k, v in google.events.items() if v["summary"] == "Design review")
    google.events[gid] = {"id": gid, "status": "cancelled"}
    await client.post(f"{API}/email/sync", headers=h)
    events = (await client.get(f"{API}/calendar/events", params=rng, headers=h)).json()["events"]
    assert events == []


async def test_time_block_task(client: AsyncClient) -> None:
    h = await auth_headers(client)
    task = (
        await client.post(f"{API}/tasks", json={"title": "Write threat model"}, headers=h)
    ).json()
    start = datetime.now(UTC) + timedelta(days=1)
    r = await client.post(
        f"{API}/calendar/time-block",
        json={"task_id": task["id"], "starts_at": start.isoformat(), "minutes": 90},
        headers=h,
    )
    assert r.status_code == 201
    ev = r.json()
    assert ev["title"] == "Focus: Write threat model" and ev["task_id"] == task["id"]
    assert ev["source"] == "time_block"


async def test_assistant_calendar_changes_need_approval(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    cid = (await client.post(f"{API}/chat/conversations", headers=h)).json()["id"]
    tomorrow = (datetime.now(IST).date() + timedelta(days=1)).isoformat()
    model.push(
        [
            {
                "name": "calendar_create_event",
                "input": {"title": "Gym", "start": f"{tomorrow}T07:00", "minutes": 60},
            }
        ]
    )
    r = await client.post(
        f"{API}/chat/conversations/{cid}/messages", json={"text": "add gym tomorrow 7am"}, headers=h
    )
    assert '"approval.required"' in r.text
    approval = (await client.get(f"{API}/approvals?status=pending", headers=h)).json()[0]
    assert approval["summary"] == f"Add “Gym” on {tomorrow} at 07:00"
    model.push("Added Gym tomorrow at 7.")
    r = await client.post(
        f"{API}/approvals/{approval['id']}/decide", json={"approve": True}, headers=h
    )
    assert r.status_code == 200
    day = date.fromisoformat(tomorrow)
    rng = {"start": _at(day, 0).isoformat(), "end": _at(day, 23).isoformat()}
    events = (await client.get(f"{API}/calendar/events", params=rng, headers=h)).json()["events"]
    assert [e["title"] for e in events] == ["Gym"]
    assert events[0]["starts_at"].startswith(_at(day, 7).isoformat()[:16])
