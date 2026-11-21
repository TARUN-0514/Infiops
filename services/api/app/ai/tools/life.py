"""Phase 5 tools: money, workouts, body metrics and habits. All local-only: this data
never reaches the cloud model. No tool here moves money."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.timeutil import now_local
from app.ai.tools.registry import Tool, ToolContext, ToolRegistry
from app.models import Habit, HealthLog
from app.services import finance, fitness


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _today(ctx: ToolContext) -> date:
    return now_local(ctx.user.timezone).date()


def _money(d: Decimal) -> str:
    return f"₹{d:,.2f}".replace(".00", "")


class AddTxIn(_In):
    amount: Decimal = Field(gt=0, le=Decimal("100000000"), description="Amount in rupees")
    description: str = Field(min_length=1, max_length=300, description="What it was for")
    kind: Literal["expense", "income"] = "expense"
    category: str | None = Field(
        None, description="One of the finance categories; guessed if empty"
    )
    day: date | None = Field(None, description="Defaults to today")


async def finance_add_transaction(ctx: ToolContext, a: AddTxIn) -> dict[str, Any]:
    tx = await finance.add_transaction(
        ctx.db,
        ctx.user.id,
        kind=a.kind,
        amount=a.amount,
        occurred_on=a.day or _today(ctx),
        description=a.description,
        category=a.category or finance.guess_category(a.description, a.kind),
        source="voice" if ctx.voice else "chat",
    )
    return {
        "id": str(tx.id),
        "kind": tx.kind,
        "amount": str(tx.amount),
        "category": tx.category,
        "day": tx.occurred_on.isoformat(),
    }


class SummaryIn(_In):
    month: str | None = Field(
        None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM, default this month"
    )


async def finance_summary(ctx: ToolContext, a: SummaryIn) -> dict[str, Any]:
    today = _today(ctx)
    s = await finance.month_summary(ctx.db, ctx.user.id, a.month or today.strftime("%Y-%m"), today)
    return {
        k: s[k]
        for k in ("month", "income", "expense", "net", "count", "categories", "over_budget")
        if k in s
    }


class SetIn(_In):
    exercise: str = Field(min_length=1, max_length=80)
    reps: int | None = Field(None, ge=0, le=1000)
    weight_kg: Decimal | None = Field(None, ge=0, le=1000)
    seconds: int | None = Field(None, ge=0, le=86400)
    distance_km: Decimal | None = Field(None, ge=0, le=1000)


class WorkoutIn(_In):
    title: str = Field("Workout", max_length=80)
    day: date | None = None
    minutes: int | None = Field(None, ge=1, le=1440)
    sets: list[SetIn] = Field(min_length=1, max_length=100, description="One entry per set")


async def fitness_log_workout(ctx: ToolContext, a: WorkoutIn) -> dict[str, Any]:
    s = await fitness.save_session(
        ctx.db,
        ctx.user.id,
        day=a.day or _today(ctx),
        title=a.title,
        minutes=a.minutes,
        notes=None,
        sets=[x.model_dump() for x in a.sets],
    )
    sets = await fitness.sets_for(ctx.db, [s.id])
    out = fitness.session_out(s, sets.get(s.id, []))
    return {
        "id": out["id"],
        "day": out["day"],
        "sets": len(out["sets"]),
        "volume_kg": out["volume_kg"],
    }


class MetricIn(_In):
    metric: Literal[
        "weight_kg", "body_fat_pct", "waist_cm", "calories", "protein_g", "water_ml", "sleep_hours"
    ]
    value: Decimal = Field(gt=0)
    day: date | None = None


async def fitness_log_metric(ctx: ToolContext, a: MetricIn) -> dict[str, Any]:
    fitness.check_metric(a.metric, a.value)
    x = HealthLog(
        user_id=ctx.user.id,
        day=a.day or _today(ctx),
        metric=a.metric,
        value=a.value,
        source="voice" if ctx.voice else "chat",
    )
    ctx.db.add(x)
    await ctx.db.flush()
    return {"id": str(x.id), "metric": x.metric, "value": str(x.value), "day": x.day.isoformat()}


class HabitTickIn(_In):
    habit: str = Field(min_length=1, max_length=80, description="Habit name")
    day: date | None = None
    done: bool = True


async def habit_tick(ctx: ToolContext, a: HabitTickIn) -> dict[str, Any]:
    day = a.day or _today(ctx)
    if day > _today(ctx):
        raise ValueError("Can't tick a habit for a future day.")
    habits = list(
        await ctx.db.scalars(
            select(Habit).where(Habit.user_id == ctx.user.id, Habit.archived.is_(False))
        )
    )
    match = [h for h in habits if h.name.lower() == a.habit.strip().lower()] or [
        h for h in habits if a.habit.strip().lower() in h.name.lower()
    ]
    if len(match) != 1:
        names = ", ".join(h.name for h in habits) or "none yet"
        raise LookupError(f"No single habit matches '{a.habit}'. Habits: {names}.")
    await fitness.set_habit(ctx.db, match[0], day, a.done)
    return {"habit": match[0].name, "day": day.isoformat(), "done": a.done}


class NoIn(_In):
    pass


async def fitness_week(ctx: ToolContext, _: NoIn) -> dict[str, Any]:
    today = _today(ctx)
    return await fitness.week_report(ctx.db, ctx.user.id, today - timedelta(days=today.weekday()))


def register(r: ToolRegistry) -> None:
    def add(name: str, desc: str, risk: Any, model: Any, fn: Any, summary: Any) -> None:
        r.register(Tool(name, desc, risk, model, fn, summary, local_only=True))

    add(
        "finance_add_transaction",
        "Record money the owner spent or received (manual or spoken entry). Never moves money.",
        "reversible",
        AddTxIn,
        finance_add_transaction,
        lambda a: f"Record {a.kind} {_money(a.amount)}: {a.description[:50]}",
    )
    add(
        "finance_summary",
        "This month's (or a given month's) income, spending by category and budgets.",
        "read",
        SummaryIn,
        finance_summary,
        lambda a: "Read spending summary",
    )
    add(
        "fitness_log_workout",
        "Log a workout with its sets (exercise, reps, weight in kg, time or distance).",
        "reversible",
        WorkoutIn,
        fitness_log_workout,
        lambda a: f"Log workout: {a.title} ({len(a.sets)} sets)",
    )
    add(
        "fitness_log_metric",
        "Log body weight, body fat, waist, calories, protein, water or sleep for a day.",
        "reversible",
        MetricIn,
        fitness_log_metric,
        lambda a: f"Log {a.metric} {a.value}",
    )
    add(
        "habit_tick",
        "Mark one of the owner's habits as done (or not done) for a day.",
        "reversible",
        HabitTickIn,
        habit_tick,
        lambda a: f"Tick habit {a.habit}",
    )
    add(
        "fitness_week",
        "This week's training, body metrics, food, sleep and habits compared with last week. "
        "Tracking only, not medical advice.",
        "read",
        NoIn,
        fitness_week,
        lambda a: "Read weekly fitness report",
    )
