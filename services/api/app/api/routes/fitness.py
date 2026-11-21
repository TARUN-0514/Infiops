"""Fitness and habits: workouts, exercise library, health logs, habits and the weekly report.
Tracking only, not medical advice."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.ai.timeutil import now_local
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import Exercise, Habit, HealthLog, WorkoutSession
from app.services import finance, fitness

router = APIRouter(tags=["fitness"])
Metric = Literal[
    "weight_kg", "body_fat_pct", "waist_cm", "calories", "protein_g", "water_ml", "sleep_hours"
]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _today(auth: Auth) -> date:
    return now_local(auth.user.timezone).date()


def _range(auth: Auth, start: date | None, end: date | None, days: int = 30) -> tuple[date, date]:
    end = end or _today(auth)
    start = start or end - timedelta(days=days - 1)
    if start > end or (end - start).days > 400:
        bad_request("Pick a range of up to 400 days.")
    return start, end


# --- exercises ------------------------------------------------------------------------


class ExerciseIn(_In):
    name: str = Field(min_length=2, max_length=80)
    muscle: str = Field("Other", max_length=30)
    equipment: str = Field("Other", max_length=30)


@router.get("/fitness/exercises")
async def exercises(db: DB, auth: Auth) -> list[dict[str, Any]]:
    return await fitness.library(db, auth.user.id)


@router.post("/fitness/exercises", status_code=status.HTTP_201_CREATED)
async def add_exercise(body: ExerciseIn, db: DB, auth: Auth) -> dict[str, Any]:
    ex = Exercise(
        user_id=auth.user.id, name=body.name.strip(), muscle=body.muscle, equipment=body.equipment
    )
    db.add(ex)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have an exercise with that name.")
    return {
        "id": str(ex.id),
        "name": ex.name,
        "muscle": ex.muscle,
        "equipment": ex.equipment,
        "custom": True,
    }


@router.delete("/fitness/exercises/{eid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(eid: uuid.UUID, db: DB, auth: Auth) -> None:
    ex = await db.get(Exercise, eid)
    if ex is None or ex.user_id != auth.user.id:
        not_found("Exercise not found.")
    await db.delete(ex)
    await db.commit()


# --- workouts ---------------------------------------------------------------------------


class SetIn(_In):
    exercise: str = Field(min_length=1, max_length=80)
    reps: int | None = Field(None, ge=0, le=1000)
    weight_kg: Decimal | None = Field(None, ge=0, le=1000, decimal_places=2)
    seconds: int | None = Field(None, ge=0, le=86400)
    distance_km: Decimal | None = Field(None, ge=0, le=1000, decimal_places=2)

    @model_validator(mode="after")
    def something(self) -> SetIn:
        if not (self.reps or self.seconds or self.distance_km):
            raise ValueError("Each set needs reps, time or distance.")
        return self


class SessionIn(_In):
    day: date
    title: str = Field("Workout", max_length=80)
    minutes: int | None = Field(None, ge=1, le=1440)
    notes: str | None = Field(None, max_length=2000)
    sets: list[SetIn] = Field(min_length=1, max_length=200)


async def _sessions_out(db: DB, rows: list[WorkoutSession]) -> list[dict[str, Any]]:
    sets = await fitness.sets_for(db, [s.id for s in rows])
    return [fitness.session_out(s, sets.get(s.id, [])) for s in rows]


@router.get("/fitness/workouts")
async def list_workouts(
    db: DB, auth: Auth, start: date | None = None, end: date | None = None
) -> list[dict[str, Any]]:
    a, b = _range(auth, start, end, 60)
    return await _sessions_out(db, await fitness.sessions_between(db, auth.user.id, a, b))


@router.post("/fitness/workouts", status_code=status.HTTP_201_CREATED)
async def create_workout(body: SessionIn, db: DB, auth: Auth) -> dict[str, Any]:
    s = await fitness.save_session(
        db,
        auth.user.id,
        day=body.day,
        title=body.title,
        minutes=body.minutes,
        notes=body.notes,
        sets=[x.model_dump() for x in body.sets],
    )
    await db.commit()
    return (await _sessions_out(db, [s]))[0]


async def _session(db: DB, auth: Auth, sid: uuid.UUID) -> WorkoutSession:
    try:
        return await fitness.owned_session(db, auth.user.id, sid)
    except LookupError:
        not_found("Workout not found.")


@router.put("/fitness/workouts/{sid}")
async def update_workout(sid: uuid.UUID, body: SessionIn, db: DB, auth: Auth) -> dict[str, Any]:
    s = await fitness.save_session(
        db,
        auth.user.id,
        day=body.day,
        title=body.title,
        minutes=body.minutes,
        notes=body.notes,
        sets=[x.model_dump() for x in body.sets],
        session=await _session(db, auth, sid),
    )
    await db.commit()
    return (await _sessions_out(db, [s]))[0]


@router.delete("/fitness/workouts/{sid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(sid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _session(db, auth, sid))
    await db.commit()


@router.get("/fitness/bests")
async def personal_bests(db: DB, auth: Auth) -> dict[str, dict[str, Any]]:
    return await fitness.bests(db, auth.user.id)


# --- health logs ------------------------------------------------------------------------


class LogIn(_In):
    day: date
    metric: Metric
    value: Decimal = Field(gt=0, le=100000, decimal_places=2)
    note: str | None = Field(None, max_length=500)


def log_out(x: HealthLog) -> dict[str, Any]:
    return {
        "id": str(x.id),
        "day": x.day.isoformat(),
        "metric": x.metric,
        "value": x.value,
        "note": x.note,
    }


@router.get("/fitness/metrics")
async def metric_specs(auth: Auth) -> dict[str, Any]:
    return {"metrics": fitness.METRICS, "today": _today(auth).isoformat()}


@router.get("/fitness/logs")
async def list_logs(
    db: DB,
    auth: Auth,
    metric: Metric | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    a, b = _range(auth, start, end, 30)
    rows = await fitness.logs_between(db, auth.user.id, a, b, metric)
    daily = fitness.daily_values(rows)
    return {
        "start": a.isoformat(),
        "end": b.isoformat(),
        "entries": [log_out(x) for x in reversed(rows)],
        "daily": {
            m: [{"day": d.isoformat(), "value": v} for d, v in sorted(days.items())]
            for m, days in daily.items()
        },
    }


@router.post("/fitness/logs", status_code=status.HTTP_201_CREATED)
async def add_log(body: LogIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        fitness.check_metric(body.metric, body.value)
    except ValueError as exc:
        bad_request(str(exc))
    x = HealthLog(user_id=auth.user.id, **body.model_dump())
    db.add(x)
    await db.commit()
    return log_out(x)


@router.delete("/fitness/logs/{lid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(lid: uuid.UUID, db: DB, auth: Auth) -> None:
    x = await db.get(HealthLog, lid)
    if x is None or x.user_id != auth.user.id:
        not_found("Entry not found.")
    await db.delete(x)
    await db.commit()


# --- habits -------------------------------------------------------------------------------


class HabitIn(_In):
    name: str = Field(min_length=1, max_length=80)
    per_week: int = Field(7, ge=1, le=7)
    archived: bool = False


@router.get("/habits")
async def list_habits(
    db: DB, auth: Auth, days: Annotated[int, Query(ge=7, le=120)] = 28
) -> dict[str, Any]:
    today = _today(auth)
    start = today - timedelta(days=days - 1)
    habits = list(
        await db.scalars(
            select(Habit)
            .where(Habit.user_id == auth.user.id)
            .order_by(Habit.archived, Habit.created_at)
        )
    )
    done = await fitness.habit_days(db, [h.id for h in habits], start - timedelta(days=400), today)
    week_start = today - timedelta(days=today.weekday())
    return {
        "today": today.isoformat(),
        "start": start.isoformat(),
        "habits": [
            {
                "id": str(h.id),
                "name": h.name,
                "per_week": h.per_week,
                "archived": h.archived,
                "days": sorted(d.isoformat() for d in done.get(h.id, set()) if d >= start),
                "streak": fitness.streak(done.get(h.id, set()), today),
                "this_week": sum(1 for d in done.get(h.id, set()) if d >= week_start),
            }
            for h in habits
        ],
    }


@router.post("/habits", status_code=status.HTTP_201_CREATED)
async def create_habit(body: HabitIn, db: DB, auth: Auth) -> dict[str, str]:
    h = Habit(user_id=auth.user.id, **body.model_dump())
    db.add(h)
    await db.commit()
    return {"id": str(h.id)}


async def _habit(db: DB, auth: Auth, hid: uuid.UUID) -> Habit:
    try:
        return await fitness.owned_habit(db, auth.user.id, hid)
    except LookupError:
        not_found("Habit not found.")


@router.patch("/habits/{hid}")
async def update_habit(hid: uuid.UUID, body: HabitIn, db: DB, auth: Auth) -> dict[str, str]:
    h = await _habit(db, auth, hid)
    for k, v in body.model_dump().items():
        setattr(h, k, v)
    await db.commit()
    return {"id": str(h.id)}


@router.delete("/habits/{hid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(hid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _habit(db, auth, hid))
    await db.commit()


class TickIn(_In):
    day: date
    done: bool


@router.put("/habits/{hid}/days")
async def tick_habit(hid: uuid.UUID, body: TickIn, db: DB, auth: Auth) -> dict[str, Any]:
    if body.day > _today(auth):
        bad_request("You can't tick a habit for a future day.")
    h = await _habit(db, auth, hid)
    await fitness.set_habit(db, h, body.day, body.done)
    await db.commit()
    return {"id": str(h.id), "day": body.day.isoformat(), "done": body.done}


# --- weekly report --------------------------------------------------------------------------


@router.get("/fitness/report")
async def weekly_report(db: DB, auth: Auth, week_of: date | None = None) -> dict[str, Any]:
    d = week_of or _today(auth)
    return await fitness.week_report(db, auth.user.id, d - timedelta(days=d.weekday()))


# --- month tracking calendar (the Phase 5 gate) -----------------------------------------------


@router.get("/tracking/month")
async def tracking_month(
    db: DB, auth: Auth, month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]
) -> dict[str, Any]:
    """Which days of a month have spending and workouts logged."""
    try:
        start, end = finance.month_bounds(month)
    except ValueError as exc:
        bad_request(str(exc))
    txs = await finance.transactions_between(db, auth.user.id, start, end)
    sessions = await fitness.sessions_between(db, auth.user.id, start, end)
    logs = await fitness.logs_between(db, auth.user.id, start, end, None)
    today = _today(auth)
    days = []
    d = start
    while d <= end:
        days.append(
            {
                "day": d.isoformat(),
                "future": d > today,
                "spending": sum(1 for t in txs if t.occurred_on == d and t.kind == "expense"),
                "workouts": sum(1 for s in sessions if s.day == d),
                "logs": sum(1 for x in logs if x.day == d),
            }
        )
        d += timedelta(days=1)
    past = [x for x in days if not x["future"]]
    return {
        "month": month,
        "days": days,
        "days_so_far": len(past),
        "spending_days": sum(1 for x in past if x["spending"]),
        "workout_days": sum(1 for x in past if x["workouts"]),
        "tracked_days": sum(1 for x in past if x["spending"] or x["workouts"] or x["logs"]),
    }
