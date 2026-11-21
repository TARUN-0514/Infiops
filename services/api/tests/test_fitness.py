"""Fitness and habits: workouts with sets, bests, health logs, habits, weekly report, gate calendar."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.ai.providers import ScriptedProvider
from app.ai.timeutil import now_local
from app.db.session import get_sessionmaker
from app.services import fitness
from tests.conftest import auth_headers
from tests.test_chat import _conv, _send

API = "/api/v1"


def _today() -> date:
    return now_local("Asia/Kolkata").date()


def _workout(day: date, weight: str = "60", **extra: Any) -> dict[str, Any]:
    return {
        "day": day.isoformat(),
        "title": "Push",
        "minutes": 50,
        "sets": [
            {"exercise": "Barbell bench press", "reps": 8, "weight_kg": weight},
            {"exercise": "Barbell bench press", "reps": 6, "weight_kg": str(Decimal(weight) + 5)},
            {"exercise": "Treadmill run", "seconds": 600, "distance_km": "1.6"},
        ],
        **extra,
    }


async def test_workouts_bests_and_encryption(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = _today()
    r = await client.post(
        f"{API}/fitness/workouts", json=_workout(today, notes="felt strong"), headers=h
    )
    assert r.status_code == 201, r.text
    w = r.json()
    assert len(w["sets"]) == 3 and Decimal(w["volume_kg"]) == Decimal(8 * 60 + 6 * 65)
    await client.post(
        f"{API}/fitness/workouts", json=_workout(today - timedelta(days=3), "70"), headers=h
    )
    bests = (await client.get(f"{API}/fitness/bests", headers=h)).json()
    assert Decimal(bests["Barbell bench press"]["weight_kg"]) == 75

    r = await client.put(
        f"{API}/fitness/workouts/{w['id']}",
        json={**_workout(today), "sets": [{"exercise": "Push-up", "reps": 20}]},
        headers=h,
    )
    assert r.status_code == 200 and len(r.json()["sets"]) == 1
    listed = (await client.get(f"{API}/fitness/workouts", headers=h)).json()
    assert [x["day"] for x in listed] == sorted((x["day"] for x in listed), reverse=True) and len(
        listed
    ) == 2

    async with get_sessionmaker()() as db:
        raw = (
            (
                await db.execute(
                    text("SELECT weight_kg FROM workout_sets WHERE weight_kg IS NOT NULL")
                )
            )
            .scalars()
            .all()
        )
        notes = (await db.execute(text("SELECT notes FROM workout_sessions"))).scalars().all()
    assert raw and all(isinstance(x, bytes) and b"70" not in x for x in raw)
    assert all(n is None or b"strong" not in n for n in notes)

    bad = await client.post(
        f"{API}/fitness/workouts",
        json={**_workout(today), "sets": [{"exercise": "Squat"}]},
        headers=h,
    )
    assert bad.status_code == 422
    bad = await client.post(
        f"{API}/fitness/workouts", json={**_workout(today), "sets": []}, headers=h
    )
    assert bad.status_code == 422
    assert (await client.delete(f"{API}/fitness/workouts/{w['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{API}/fitness/workouts/{w['id']}", headers=h)).status_code == 404


async def test_exercise_library_and_custom(client: AsyncClient) -> None:
    h = await auth_headers(client)
    lib = (await client.get(f"{API}/fitness/exercises", headers=h)).json()
    assert len(lib) >= 30 and not any(x.get("custom") for x in lib)
    r = await client.post(
        f"{API}/fitness/exercises",
        json={"name": "Landmine press", "muscle": "Shoulders"},
        headers=h,
    )
    assert r.status_code == 201
    assert (
        await client.post(f"{API}/fitness/exercises", json={"name": "Landmine press"}, headers=h)
    ).status_code == 400
    lib = (await client.get(f"{API}/fitness/exercises", headers=h)).json()
    assert any(x["name"] == "Landmine press" and x["custom"] for x in lib)


async def test_health_logs_validate_and_sum(client: AsyncClient) -> None:
    h = await auth_headers(client)
    d = _today().isoformat()
    for metric, value in [
        ("water_ml", "500"),
        ("water_ml", "750"),
        ("weight_kg", "78.4"),
        ("sleep_hours", "7.5"),
    ]:
        r = await client.post(
            f"{API}/fitness/logs", json={"day": d, "metric": metric, "value": value}, headers=h
        )
        assert r.status_code == 201, r.text
    r = await client.post(
        f"{API}/fitness/logs", json={"day": d, "metric": "weight_kg", "value": "900"}, headers=h
    )
    assert r.status_code == 400
    r = await client.post(
        f"{API}/fitness/logs", json={"day": d, "metric": "mood", "value": "5"}, headers=h
    )
    assert r.status_code == 422
    out = (await client.get(f"{API}/fitness/logs", headers=h)).json()
    assert Decimal(out["daily"]["water_ml"][0]["value"]) == 1250  # water adds up over the day
    assert Decimal(out["daily"]["weight_kg"][0]["value"]) == Decimal("78.4")
    async with get_sessionmaker()() as db:
        raw = (await db.execute(text("SELECT value FROM health_logs"))).scalars().all()
    assert all(isinstance(v, bytes) and b"78.4" not in v for v in raw)


def test_streak() -> None:
    t = date(2026, 11, 21)
    days = {t - timedelta(days=i) for i in range(1, 5)}
    assert fitness.streak(days, t) == 4  # today not ticked yet doesn't break it
    assert fitness.streak(days | {t}, t) == 5
    assert fitness.streak({t - timedelta(days=2)}, t) == 0


async def test_habits(client: AsyncClient) -> None:
    h = await auth_headers(client)
    hid = (
        await client.post(f"{API}/habits", json={"name": "Read 20 pages", "per_week": 5}, headers=h)
    ).json()["id"]
    today = _today()
    for i in range(3):
        r = await client.put(
            f"{API}/habits/{hid}/days",
            json={"day": (today - timedelta(days=i)).isoformat(), "done": True},
            headers=h,
        )
        assert r.status_code == 200
    r = await client.put(
        f"{API}/habits/{hid}/days",
        json={"day": (today + timedelta(days=1)).isoformat(), "done": True},
        headers=h,
    )
    assert r.status_code == 400
    habit = (await client.get(f"{API}/habits", headers=h)).json()["habits"][0]
    assert habit["streak"] == 3 and len(habit["days"]) == 3
    await client.put(
        f"{API}/habits/{hid}/days", json={"day": today.isoformat(), "done": False}, headers=h
    )
    habit = (await client.get(f"{API}/habits", headers=h)).json()["habits"][0]
    assert habit["streak"] == 2


async def test_weekly_report_and_gate_calendar(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = _today()
    monday = today - timedelta(days=today.weekday())
    await client.post(f"{API}/fitness/workouts", json=_workout(monday), headers=h)
    await client.post(
        f"{API}/fitness/workouts", json=_workout(monday - timedelta(days=7)), headers=h
    )
    await client.post(
        f"{API}/fitness/logs",
        json={"day": monday.isoformat(), "metric": "weight_kg", "value": "80"},
        headers=h,
    )
    rep = (await client.get(f"{API}/fitness/report", headers=h)).json()
    assert rep["week_start"] == monday.isoformat() and rep["this_week"]["workouts"] == 1
    assert rep["last_week"]["workouts"] == 1 and "Not medical advice" in rep["note"]

    await client.post(
        f"{API}/finance/transactions",
        json={
            "kind": "expense",
            "amount": "99",
            "occurred_on": today.isoformat(),
            "description": "chai",
        },
        headers=h,
    )
    cal = (
        await client.get(
            f"{API}/tracking/month", params={"month": today.strftime("%Y-%m")}, headers=h
        )
    ).json()
    day = next(d for d in cal["days"] if d["day"] == today.isoformat())
    assert day["spending"] == 1 and cal["spending_days"] == 1
    assert cal["days_so_far"] == today.day and cal["tracked_days"] >= 1


async def test_chat_logs_workout_and_metric(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    cid = await _conv(client, h)
    model.push(
        [
            {
                "name": "fitness_log_workout",
                "input": {
                    "title": "Legs",
                    "sets": [{"exercise": "Barbell back squat", "reps": 5, "weight_kg": "100"}],
                },
            },
            {"name": "fitness_log_metric", "input": {"metric": "weight_kg", "value": "79"}},
        ],
        "Logged.",
    )
    events = await _send(client, h, cid, "did squats 5x100 and weighed 79")
    done = [e for e in events if e["type"] == "tool.finished"]
    assert [d["status"] for d in done] == ["succeeded", "succeeded"]
    assert len((await client.get(f"{API}/fitness/workouts", headers=h)).json()) == 1
