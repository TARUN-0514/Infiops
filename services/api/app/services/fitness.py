"""Fitness: workouts with sets, an exercise library, health logs, habits and a weekly report.
Numbers come only from what the owner logged. This is tracking, not medical advice."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Exercise, Habit, HabitLog, HealthLog, WorkoutSession, WorkoutSet

METRICS: dict[str, dict[str, Any]] = {
    "weight_kg": {"label": "Body weight", "unit": "kg", "min": 20, "max": 400, "sum": False},
    "body_fat_pct": {"label": "Body fat", "unit": "%", "min": 2, "max": 70, "sum": False},
    "waist_cm": {"label": "Waist", "unit": "cm", "min": 30, "max": 250, "sum": False},
    "calories": {"label": "Calories", "unit": "kcal", "min": 1, "max": 10000, "sum": True},
    "protein_g": {"label": "Protein", "unit": "g", "min": 0, "max": 1000, "sum": True},
    "water_ml": {"label": "Water", "unit": "ml", "min": 50, "max": 10000, "sum": True},
    "sleep_hours": {"label": "Sleep", "unit": "h", "min": 0.5, "max": 24, "sum": True},
}

# Built-in library: (name, muscle, equipment). The owner can add their own.
LIBRARY: list[tuple[str, str, str]] = [
    ("Barbell bench press", "Chest", "Barbell"),
    ("Incline dumbbell press", "Chest", "Dumbbell"),
    ("Push-up", "Chest", "Bodyweight"),
    ("Chest fly (cable)", "Chest", "Cable"),
    ("Barbell back squat", "Legs", "Barbell"),
    ("Leg press", "Legs", "Machine"),
    ("Romanian deadlift", "Legs", "Barbell"),
    ("Walking lunge", "Legs", "Dumbbell"),
    ("Leg curl", "Legs", "Machine"),
    ("Leg extension", "Legs", "Machine"),
    ("Calf raise", "Legs", "Machine"),
    ("Deadlift", "Back", "Barbell"),
    ("Pull-up", "Back", "Bodyweight"),
    ("Lat pulldown", "Back", "Cable"),
    ("Barbell row", "Back", "Barbell"),
    ("Seated cable row", "Back", "Cable"),
    ("Overhead press", "Shoulders", "Barbell"),
    ("Lateral raise", "Shoulders", "Dumbbell"),
    ("Face pull", "Shoulders", "Cable"),
    ("Barbell curl", "Arms", "Barbell"),
    ("Hammer curl", "Arms", "Dumbbell"),
    ("Triceps pushdown", "Arms", "Cable"),
    ("Dips", "Arms", "Bodyweight"),
    ("Plank", "Core", "Bodyweight"),
    ("Hanging leg raise", "Core", "Bodyweight"),
    ("Cable crunch", "Core", "Cable"),
    ("Running", "Cardio", "None"),
    ("Cycling", "Cardio", "Machine"),
    ("Rowing machine", "Cardio", "Machine"),
    ("Walking", "Cardio", "None"),
    ("Skipping", "Cardio", "Rope"),
    ("Swimming", "Cardio", "None"),
]


def check_metric(metric: str, value: Decimal) -> None:
    spec = METRICS.get(metric)
    if spec is None:
        raise ValueError(f"Unknown measurement. Use one of: {', '.join(METRICS)}.")
    if not spec["min"] <= value <= spec["max"]:
        raise ValueError(
            f"{spec['label']} should be between {spec['min']} and {spec['max']} {spec['unit']}."
        )


async def library(db: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    own = list(
        await db.scalars(
            select(Exercise).where(Exercise.user_id == user_id).order_by(Exercise.name)
        )
    )
    out = [{"name": n, "muscle": m, "equipment": e, "custom": False} for n, m, e in LIBRARY]
    names = {n.lower() for n, _, _ in LIBRARY}
    out += [
        {
            "id": str(x.id),
            "name": x.name,
            "muscle": x.muscle,
            "equipment": x.equipment,
            "custom": True,
        }
        for x in own
        if x.name.lower() not in names
    ]
    return sorted(out, key=lambda x: (x["muscle"], x["name"]))


async def owned_session(db: AsyncSession, user_id: uuid.UUID, sid: uuid.UUID) -> WorkoutSession:
    s = await db.get(WorkoutSession, sid)
    if s is None or s.user_id != user_id:
        raise LookupError("Workout not found.")
    return s


async def save_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    day: date,
    title: str,
    minutes: int | None,
    notes: str | None,
    sets: list[dict[str, Any]],
    session: WorkoutSession | None = None,
) -> WorkoutSession:
    if not sets:
        raise ValueError("Add at least one set.")
    if session is None:
        session = WorkoutSession(user_id=user_id, day=day)
        db.add(session)
    session.day, session.title = day, title.strip()[:80] or "Workout"
    session.minutes, session.notes = minutes, (notes or "").strip() or None
    await db.flush()
    await db.execute(delete(WorkoutSet).where(WorkoutSet.session_id == session.id))
    for i, s in enumerate(sets):
        name = str(s.get("exercise", "")).strip()[:80]
        if not name:
            raise ValueError(f"Set {i + 1} needs an exercise.")
        if not any(s.get(k) for k in ("reps", "seconds", "distance_km")):
            raise ValueError(f"Set {i + 1} ({name}) needs reps, time or distance.")
        db.add(
            WorkoutSet(
                session_id=session.id,
                position=i,
                exercise=name,
                reps=s.get("reps"),
                weight_kg=s.get("weight_kg"),
                seconds=s.get("seconds"),
                distance_km=s.get("distance_km"),
            )
        )
    await db.flush()
    return session


async def sets_for(
    db: AsyncSession, session_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[WorkoutSet]]:
    out: dict[uuid.UUID, list[WorkoutSet]] = defaultdict(list)
    if session_ids:
        for s in await db.scalars(
            select(WorkoutSet)
            .where(WorkoutSet.session_id.in_(session_ids))
            .order_by(WorkoutSet.position)
        ):
            out[s.session_id].append(s)
    return out


def volume(sets: list[WorkoutSet]) -> Decimal:
    return sum(((s.weight_kg or Decimal(0)) * (s.reps or 0) for s in sets), Decimal(0))


def session_out(s: WorkoutSession, sets: list[WorkoutSet]) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "day": s.day.isoformat(),
        "title": s.title,
        "minutes": s.minutes,
        "notes": s.notes,
        "volume_kg": volume(sets),
        "sets": [
            {
                "exercise": x.exercise,
                "reps": x.reps,
                "weight_kg": x.weight_kg,
                "seconds": x.seconds,
                "distance_km": x.distance_km,
            }
            for x in sets
        ],
    }


async def sessions_between(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[WorkoutSession]:
    return list(
        await db.scalars(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.day >= start,
                WorkoutSession.day <= end,
            )
            .order_by(WorkoutSession.day.desc(), WorkoutSession.created_at.desc())
        )
    )


async def bests(db: AsyncSession, user_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    """Heaviest set per exercise (and its reps), from everything logged."""
    rows = await db.execute(
        select(WorkoutSet, WorkoutSession.day)
        .join(WorkoutSession, WorkoutSession.id == WorkoutSet.session_id)
        .where(WorkoutSession.user_id == user_id)
    )
    out: dict[str, dict[str, Any]] = {}
    for s, day in rows.tuples():
        if s.weight_kg is None:
            continue
        cur = out.get(s.exercise)
        if cur is None or s.weight_kg > cur["weight_kg"]:
            out[s.exercise] = {"weight_kg": s.weight_kg, "reps": s.reps, "day": day.isoformat()}
    return out


async def logs_between(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date, metric: str | None = None
) -> list[HealthLog]:
    q = select(HealthLog).where(
        HealthLog.user_id == user_id, HealthLog.day >= start, HealthLog.day <= end
    )
    if metric:
        q = q.where(HealthLog.metric == metric)
    return list(await db.scalars(q.order_by(HealthLog.day, HealthLog.created_at)))


def daily_values(logs: list[HealthLog]) -> dict[str, dict[date, Decimal]]:
    """Per metric and day: totals for food, water and sleep; latest reading for body measures."""
    out: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for log in logs:
        day_map = out[log.metric]
        if METRICS[log.metric]["sum"]:
            day_map[log.day] = day_map.get(log.day, Decimal(0)) + log.value
        else:
            day_map[log.day] = log.value
    return out


# --- habits ---------------------------------------------------------------------------


async def owned_habit(db: AsyncSession, user_id: uuid.UUID, hid: uuid.UUID) -> Habit:
    h = await db.get(Habit, hid)
    if h is None or h.user_id != user_id:
        raise LookupError("Habit not found.")
    return h


async def habit_days(
    db: AsyncSession, habit_ids: list[uuid.UUID], start: date, end: date
) -> dict[uuid.UUID, set[date]]:
    out: dict[uuid.UUID, set[date]] = defaultdict(set)
    if habit_ids:
        for log in await db.scalars(
            select(HabitLog).where(
                HabitLog.habit_id.in_(habit_ids), HabitLog.day >= start, HabitLog.day <= end
            )
        ):
            out[log.habit_id].add(log.day)
    return out


def streak(days: set[date], today: date) -> int:
    """Consecutive days ending today (or yesterday, if today isn't ticked yet)."""
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


async def set_habit(db: AsyncSession, habit: Habit, day: date, done: bool) -> None:
    existing = await db.get(HabitLog, (habit.id, day))
    if done and existing is None:
        db.add(HabitLog(habit_id=habit.id, day=day))
    elif not done and existing is not None:
        await db.delete(existing)
    await db.flush()


# --- weekly report --------------------------------------------------------------------


async def week_report(db: AsyncSession, user_id: uuid.UUID, start: date) -> dict[str, Any]:
    """Monday-to-Sunday facts from logged data, with the previous week for comparison."""
    end = start + timedelta(days=6)
    prev_start = start - timedelta(days=7)

    async def facts(a: date, b: date) -> dict[str, Any]:
        sessions = await sessions_between(db, user_id, a, b)
        sets = await sets_for(db, [s.id for s in sessions])
        logs = daily_values(await logs_between(db, user_id, a, b))
        avg = {
            m: (sum(v.values(), Decimal(0)) / len(v)).quantize(Decimal("0.1")) if v else None
            for m, v in logs.items()
        }
        weights = logs.get("weight_kg", {})
        return {
            "workouts": len(sessions),
            "minutes": sum(s.minutes or 0 for s in sessions),
            "sets": sum(len(v) for v in sets.values()),
            "volume_kg": sum((volume(v) for v in sets.values()), Decimal(0)),
            "avg": {m: avg.get(m) for m in ("calories", "protein_g", "water_ml", "sleep_hours")},
            "days_logged": {m: len(logs.get(m, {})) for m in METRICS},
            "weight_start": weights[min(weights)] if weights else None,
            "weight_end": weights[max(weights)] if weights else None,
        }

    this, last = await facts(start, end), await facts(prev_start, start - timedelta(days=1))
    habits = list(
        await db.scalars(select(Habit).where(Habit.user_id == user_id, Habit.archived.is_(False)))
    )
    done = await habit_days(db, [h.id for h in habits], start, end)
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "this_week": this,
        "last_week": last,
        "habits": [
            {"name": h.name, "done": len(done.get(h.id, set())), "target": h.per_week}
            for h in habits
        ],
        "note": "From what you logged. Not medical advice.",
    }
