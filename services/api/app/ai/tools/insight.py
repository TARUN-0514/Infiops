"""Phase 6 tools: what needs attention, and how the owner's time and work are trending."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.ai.tools.registry import Tool, ToolContext, ToolRegistry
from app.services import analytics
from app.services import insights as ins


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoIn(_In):
    pass


async def insights_list(ctx: ToolContext, _: NoIn) -> dict[str, Any]:
    found = await ins.detect(ctx.db, ctx.user)
    return {
        "insights": [
            {k: i[k] for k in ("kind", "severity", "title", "count")}
            | {"items": [f"{x['label']} ({x['sub']})" for x in i["items"]]}
            for i in found
        ],
        "note": "Computed from stored tasks, email and calendar. Empty means nothing found.",
    }


class AnalyticsIn(_In):
    days: Literal[7, 30, 90] = 30
    section: Literal["tasks", "time", "habits", "goals", "workload", "finance", "fitness"]


async def analytics_summary(ctx: ToolContext, args: AnalyticsIn) -> dict[str, Any]:
    data = await analytics.overview(ctx.db, ctx.user, args.days)
    return {"range": data["range"], args.section: data[args.section]}


def register(r: ToolRegistry) -> None:
    r.register(
        Tool(
            "insights_list",
            "What needs attention now: overdue tasks, email waiting over 2 days for a reply, "
            "calendar conflicts, overloaded days and tasks postponed 3+ times.",
            "read",
            NoIn,
            insights_list,
            lambda a: "Check what needs attention",
        )
    )
    r.register(
        Tool(
            "analytics_summary",
            "Trends from logged data for the last 7, 30 or 90 days: task completion and "
            "on-time rates, time allocation, habits, goals, workload, money or fitness.",
            "read",
            AnalyticsIn,
            analytics_summary,
            lambda a: f"Look at {a.section} for the last {a.days} days",
            local_only=True,
        )
    )
