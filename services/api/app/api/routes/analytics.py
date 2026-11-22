"""Analytics, proactive insights, check-ins and monthly reports."""

from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.gateway import get_gateway
from app.api.deps import DB, Auth
from app.api.routes.briefing import briefing_out
from app.api.routes.common import bad_request
from app.models import Briefing
from app.services import analytics, insights
from app.services import checkins as svc
from app.services.briefing import settings_for

router = APIRouter(tags=["analytics"])


def _today(auth: Auth) -> date:
    return datetime.now(ZoneInfo(auth.user.timezone)).date()


@router.get("/analytics")
async def overview(db: DB, auth: Auth, days: int = Query(30)) -> dict[str, Any]:
    if days not in analytics.RANGES:
        raise RequestValidationError(
            [{"loc": ("query", "days"), "msg": "Choose 7, 30 or 90 days.", "type": "value_error"}]
        )
    return await analytics.overview(db, auth.user, days)


@router.get("/insights")
async def list_insights(db: DB, auth: Auth) -> dict[str, Any]:
    return {
        "insights": await insights.detect(db, auth.user),
        "rules": {
            "reply_wait_hours": insights.REPLY_WAIT_HOURS,
            "postponed_min": insights.POSTPONED_MIN,
            "overload_meeting_minutes": insights.OVERLOAD_MEETING_MINUTES,
            "overload_tasks_due": insights.OVERLOAD_TASKS_DUE,
        },
    }


# --- check-ins --------------------------------------------------------------------

CheckinKind = Literal["midday", "evening"]


@router.get("/checkins/today")
async def checkins_today(db: DB, auth: Auth) -> dict[str, Any]:
    day = _today(auth)
    out: dict[str, Any] = {
        "date": day.isoformat(),
        "settings": await settings_for(db, auth.user.id),
    }
    for kind in svc.CHECKIN_KINDS:
        b = await svc.existing(db, auth.user, kind, day)
        out[kind] = briefing_out(b) if b else None
    return out


class WriteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regenerate: bool = False


@router.post("/checkins/{kind}")
async def write_checkin(kind: CheckinKind, body: WriteIn, db: DB, auth: Auth) -> dict[str, Any]:
    b = await svc.write(
        db, get_gateway(), auth.user, kind, _today(auth), regenerate=body.regenerate
    )
    await db.commit()
    return briefing_out(b)


# --- monthly reports --------------------------------------------------------------


@router.get("/reports/monthly")
async def monthly_list(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(Briefing)
        .where(Briefing.user_id == auth.user.id, Briefing.kind == "monthly")
        .order_by(Briefing.for_date.desc())
        .limit(24)
    )
    return [briefing_out(b) for b in rows]


class MonthIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str | None = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.post("/reports/monthly", status_code=201)
async def monthly_write(body: MonthIn, db: DB, auth: Auth) -> dict[str, Any]:
    today = _today(auth)
    first = (
        date(int(body.month[:4]), int(body.month[5:]), 1) if body.month else svc.prev_month(today)
    )
    if first > today:
        bad_request("That month hasn't started yet.")
    b = await svc.write(db, get_gateway(), auth.user, "monthly", first, regenerate=True)
    await db.commit()
    return briefing_out(b)
