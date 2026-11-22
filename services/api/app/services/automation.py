"""Automation workflows: what a workflow may contain, when it runs next, events, and the
{{templates}} that pass results from one step to the next."""

from __future__ import annotations

import calendar
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Events NEXUS raises itself. Filters match these payload keys (case-insensitive "contains").
EVENTS: dict[str, dict[str, Any]] = {
    "task.created": {"label": "A task is created", "fields": ["title", "priority", "project"]},
    "task.completed": {"label": "A task is completed", "fields": ["title", "project"]},
    "email.important": {"label": "An important email arrives", "fields": ["from", "subject"]},
    "finding.sla_breached": {
        "label": "A security finding passes its SLA",
        "fields": ["title", "severity", "workspace"],
    },
    "date.upcoming": {"label": "An important date is coming up", "fields": ["title", "kind"]},
}
EventName = Literal[
    "task.created", "task.completed", "email.important", "finding.sla_breached", "date.upcoming"
]
CONDITION_OPS = (
    "equals",
    "not_equals",
    "contains",
    "greater_than",
    "less_than",
    "empty",
    "not_empty",
)
BACKOFF_MINUTES = (1, 5, 15, 15, 15)
MAX_STEPS = 20


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class ManualTrigger(_In):
    type: Literal["manual"] = "manual"


class ScheduleTrigger(_In):
    type: Literal["schedule"] = "schedule"
    every: Literal["day", "month", "hours"]
    at: HHMM | None = None
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(default_factory=list, max_length=7)
    day: int | None = Field(None, ge=1, le=31)
    hours: int | None = Field(None, ge=1, le=168)

    @model_validator(mode="after")
    def complete(self) -> ScheduleTrigger:
        if self.every in ("day", "month") and not self.at:
            raise ValueError("Pick a time of day.")
        if self.every == "month" and not self.day:
            raise ValueError("Pick a day of the month.")
        if self.every == "hours" and not self.hours:
            raise ValueError("Pick how many hours apart.")
        self.weekdays = sorted(set(self.weekdays))
        return self


class EventTrigger(_In):
    type: Literal["event"] = "event"
    event: EventName
    filter: dict[Annotated[str, Field(max_length=30)], Annotated[str, Field(max_length=200)]] = (
        Field(default_factory=dict, max_length=5)
    )

    @model_validator(mode="after")
    def known_fields(self) -> EventTrigger:
        allowed = set(EVENTS[self.event]["fields"])
        bad = [k for k in self.filter if k not in allowed]
        if bad:
            raise ValueError(f"This event can be filtered by {', '.join(sorted(allowed))}.")
        return self


Trigger = Annotated[ManualTrigger | ScheduleTrigger | EventTrigger, Field(discriminator="type")]


class StepIn(_In):
    kind: Literal["tool", "agent", "condition", "approval", "notify"]
    name: str = Field("", max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    retry_max: int = Field(2, ge=0, le=5)

    @model_validator(mode="after")
    def shape(self) -> StepIn:
        c = self.config
        if len(json.dumps(c)) > 8000:
            raise ValueError("A step's settings are too long.")

        def text(key: str, required: bool = True, limit: int = 4000) -> None:
            v = c.get(key)
            if v is None and not required:
                return
            if not isinstance(v, str) or (required and not v.strip()) or len(v) > limit:
                raise ValueError(f"{self.kind.title()} step needs {key.replace('_', ' ')}.")

        if self.kind == "tool":
            text("tool", limit=80)
            if not isinstance(c.get("args", {}), dict):
                raise ValueError("Tool inputs must be an object.")
            c.setdefault("args", {})
        elif self.kind == "agent":
            text("prompt")
        elif self.kind == "condition":
            text("left", limit=500)
            if c.get("op") not in CONDITION_OPS:
                raise ValueError(f"Condition must be one of: {', '.join(CONDITION_OPS)}.")
            if c["op"] not in ("empty", "not_empty"):
                text("right", limit=500)
        elif self.kind == "approval":
            text("message", limit=500)
        elif self.kind == "notify":
            text("title", limit=200)
            text("body", required=False)
        return self


class WorkflowIn(_In):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=1000)
    trigger: Trigger
    steps: list[StepIn] = Field(min_length=1, max_length=MAX_STEPS)
    enabled: bool = True
    created_from_prompt: str | None = Field(None, max_length=2000)


# --- schedules -------------------------------------------------------------------------------


def _at(day: date, hhmm: str, zone: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=zone).astimezone(UTC)


def next_run(trigger: dict[str, Any], tz: str, after: datetime) -> datetime | None:
    """The first time strictly after `after` that a schedule fires (None if not a schedule)."""
    if trigger.get("type") != "schedule":
        return None
    t = ScheduleTrigger.model_validate(trigger)
    if t.every == "hours":
        assert t.hours
        return after + timedelta(hours=t.hours)
    zone = ZoneInfo(tz)
    local = after.astimezone(zone).date()
    assert t.at
    if t.every == "day":
        for i in range(0, 9):
            d = local + timedelta(days=i)
            if t.weekdays and d.weekday() not in t.weekdays:
                continue
            when = _at(d, t.at, zone)
            if when > after:
                return when
        return None
    assert t.day
    y, m = local.year, local.month
    for _ in range(3):
        d = date(y, m, min(t.day, calendar.monthrange(y, m)[1]))
        when = _at(d, t.at, zone)
        if when > after:
            return when
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def describe_trigger(trigger: dict[str, Any]) -> str:
    kind = trigger.get("type")
    if kind == "manual":
        return "When you run it"
    if kind == "event":
        return str(EVENTS.get(trigger.get("event", ""), {}).get("label", "On an event"))
    every = trigger.get("every")
    if every == "hours":
        n = trigger.get("hours")
        return f"Every {n} hour{'s' if n != 1 else ''}"
    if every == "month":
        return f"Monthly on day {trigger.get('day')} at {trigger.get('at')}"
    days = trigger.get("weekdays") or []
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    when = (
        "Every day"
        if not days or len(days) == 7
        else "Weekdays"
        if days == [0, 1, 2, 3, 4]
        else ", ".join(names[d] for d in days)
    )
    return f"{when} at {trigger.get('at')}"


def event_matches(trigger: dict[str, Any], event: str, payload: dict[str, Any]) -> bool:
    if trigger.get("type") != "event" or trigger.get("event") != event:
        return False
    for key, want in (trigger.get("filter") or {}).items():
        if str(want).strip().lower() not in str(payload.get(key, "")).lower():
            return False
    return True


# --- templates -------------------------------------------------------------------------------

TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def lookup(scope: dict[str, Any], path: str) -> Any:
    cur: Any = scope
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            i = int(part)
            cur = cur[i] if 0 <= i < len(cur) else None
        else:
            return None
    return cur


def render(value: Any, scope: dict[str, Any]) -> Any:
    """Fill {{trigger.x}}, {{steps.2.output.y}} and {{now.date}} in strings, lists and dicts.
    A string that is only one template keeps the value's own type."""
    if isinstance(value, dict):
        return {k: render(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, scope) for v in value]
    if not isinstance(value, str):
        return value
    whole = TEMPLATE.fullmatch(value.strip())
    if whole:
        return lookup(scope, whole.group(1))

    def sub(m: re.Match[str]) -> str:
        v = lookup(scope, m.group(1))
        if v is None:
            return ""
        return v if isinstance(v, str) else json.dumps(v, default=str)

    return TEMPLATE.sub(sub, value)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return len(v) if isinstance(v, list | dict) else None


def check(left: Any, op: str, right: Any) -> bool:
    if op == "empty":
        return left in (None, "", [], {}, 0)
    if op == "not_empty":
        return left not in (None, "", [], {}, 0)
    if op == "contains":
        if isinstance(left, list):
            return any(str(right).lower() == str(x).lower() for x in left)
        return str(right).lower() in str(left if left is not None else "").lower()
    if op in ("greater_than", "less_than"):
        a, b = _num(left), _num(right)
        if a is None or b is None:
            return False
        return a > b if op == "greater_than" else a < b
    same = str(left if left is not None else "").strip().lower() == str(right).strip().lower()
    return same if op == "equals" else not same
