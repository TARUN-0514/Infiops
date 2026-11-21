"""Phase 1 gate: does NEXUS turn 20 everyday sentences into the right tasks?

Runs the real task parser against your configured model (local by default; add
--cloud to use the cloud model) with a fixed "now" so answers are checkable.

    cd services/api && uv run python scripts/eval_task_parsing.py [--cloud]

Needs the database (for usage logging) and the model server running.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from app.ai.gateway import get_gateway
from app.ai.task_parser import parse_task
from app.db.session import dispose_engine, get_sessionmaker

TZ = "Asia/Kolkata"
# Saturday 21 November 2026, 10:00 local
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=ZoneInfo(TZ))


@dataclass
class Case:
    text: str
    title_has: list[str]
    date: str | None = None  # expected local YYYY-MM-DD, or None for no date
    time: str | None = None  # expected local HH:MM, or None for all-day / no time
    priority: str | None = None
    rrule_has: list[str] = field(default_factory=list)
    project: str | None = None
    subtasks: int | None = None
    no_date: bool = False


CASES = [
    Case("buy milk tomorrow", ["milk"], "2026-11-22"),
    Case("call mom tomorrow at 6pm", ["mom"], "2026-11-22", "18:00"),
    Case("submit the expense report by Friday", ["expense"], "2026-11-27"),
    Case("dentist appointment next Tuesday at 10:30", ["dentist"], "2026-11-24", "10:30"),
    Case(
        "pay rent on the 1st of every month",
        ["rent"],
        "2026-12-01",
        rrule_has=["MONTHLY", "BYMONTHDAY=1"],
    ),
    Case(
        "water the plants every day at 8am",
        ["water", "plant"],
        "2026-11-22",
        "08:00",
        rrule_has=["DAILY"],
    ),
    Case("urgent: renew the SSL certificate today", ["ssl"], "2026-11-21", priority="urgent"),
    Case(
        "important - review the pentest findings tomorrow morning",
        ["pentest"],
        "2026-11-22",
        "09:00",
        priority="high",
    ),
    Case(
        "gym every Monday, Wednesday and Friday at 7am",
        ["gym"],
        rrule_has=["WEEKLY", "MO", "WE", "FR"],
    ),
    Case("read chapter 5 of the OSCP guide in 3 days", ["chapter 5"], "2026-11-24"),
    Case("plan the Goa trip: book flights, book hotel, make itinerary", ["goa"], subtasks=3),
    Case("add 'patch the web server' to the Homelab project", ["patch"], project="homelab"),
    Case("remind me to file taxes on 31 July", ["tax"], "2027-07-31"),
    Case(
        "weekly team sync every Thursday at 3pm", ["sync"], time="15:00", rrule_has=["WEEKLY", "TH"]
    ),
    Case("send invoice to the client end of the month", ["invoice"], "2026-11-30"),
    Case("check the vulnerability scan results tonight", ["scan"], "2026-11-21", "20:00"),
    Case("buy a birthday gift for Priya before December 5", ["gift"], "2026-12-05"),
    Case("clean the apartment this weekend", ["clean"]),
    Case("renew my passport", ["passport"], no_date=True),
    Case(
        "every weekday at 9:15 do the standup",
        ["standup"],
        time="09:15",
        rrule_has=["WEEKLY", "MO", "TU", "WE", "TH", "FR"],
    ),
]


def check(case: Case, got: dict[str, object]) -> list[str]:
    problems: list[str] = []
    title = str(got["title"]).lower()
    for word in case.title_has:
        if word.lower() not in title:
            problems.append(f"title {got['title']!r} lacks {word!r}")
    due = got["due_at"]
    local = due.astimezone(ZoneInfo(TZ)) if isinstance(due, datetime) else None
    if case.date is not None:
        if local is None or local.strftime("%Y-%m-%d") != case.date:
            problems.append(f"date {local:%Y-%m-%d} != {case.date}" if local else "no date")
    elif (
        case.date is None
        and case.time is None
        and not case.rrule_has
        and local is not None
        and case.text in ("renew my passport",)
    ):
        problems.append("invented a date")
    if case.time is not None:
        if local is None or got["all_day"] or local.strftime("%H:%M") != case.time:
            problems.append(f"time {local:%H:%M} != {case.time}" if local else "no time")
    if case.priority and got["priority"] != case.priority:
        problems.append(f"priority {got['priority']} != {case.priority}")
    rrule = str(got["recurrence"] or "")
    for part in case.rrule_has:
        if part not in rrule:
            problems.append(f"rrule {rrule!r} lacks {part}")
    if case.project and case.project not in str(got["project_name"] or "").lower():
        problems.append(f"project {got['project_name']!r} != {case.project}")
    if case.subtasks is not None and len(got["subtasks"]) != case.subtasks:  # type: ignore[arg-type]
        problems.append(f"{len(got['subtasks'])} subtasks != {case.subtasks}")  # type: ignore[arg-type]
    return problems


async def main(cloud: bool) -> int:
    gateway = get_gateway()
    passed = 0
    async with get_sessionmaker()() as db:
        for i, case in enumerate(CASES, 1):
            try:
                got = await parse_task(
                    db,
                    gateway,
                    user_id=None,
                    text=case.text,
                    tz=TZ,
                    cloud=cloud,
                    now=NOW,
                )
                problems = check(case, got)
            except Exception as exc:  # report and keep going
                problems = [f"error: {exc}"]
            ok = not problems
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'} {i:2}. {case.text}")
            for p in problems:
                print(f"         - {p}")
        await db.commit()
    await dispose_engine()
    print(f"\n{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", action="store_true", help="use the cloud model")
    sys.exit(asyncio.run(main(ap.parse_args().cloud)))
