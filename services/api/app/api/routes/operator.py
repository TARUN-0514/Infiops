"""Computer control (policy, kill switch, activity log), research reports and GitHub status."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.tools.registry import Tool
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.integrations import github
from app.models import Device, ResearchReport, ToolExecution
from app.services import audit, jobs, operator, research
from app.services import devices as dev

router = APIRouter(tags=["operator"])

OPERATOR_TOOLS = (
    "desktop_open_app",
    "desktop_open_url",
    "files_list",
    "files_read",
    "files_write",
    "files_move",
    "browser_read",
    "browser_act",
    "computer_use",
    "claude_code_run",
)
ACTIVITY_TOOLS = (
    *OPERATOR_TOOLS,
    "web_search",
    "web_fetch",
    "research_run",
    "github_pulls",
    "github_pull",
    "github_issues",
    "github_issue",
)


async def _policy_out(db: DB, user_id: uuid.UUID) -> dict[str, Any]:
    policy = await operator.get_policy(db, user_id)
    rows = list(
        await db.scalars(
            select(Device).where(Device.user_id == user_id, Device.revoked_at.is_(None))
        )
    )
    live = await dev.presence([d.id for d in rows])
    return {
        "policy": policy.model_dump(),
        "devices": [
            {
                "id": str(d.id),
                "name": d.name,
                "online": d.id in live,
                "operator": bool(d.capabilities.get("operator")),
                "browser": bool(d.capabilities.get("browser")),
                "screen": bool(d.capabilities.get("screen")),
                "claude_code": bool(d.capabilities.get("claude_code")),
            }
            for d in rows
        ],
    }


@router.get("/operator/policy")
async def get_policy(db: DB, auth: Auth) -> dict[str, Any]:
    return await _policy_out(db, auth.user.id)


@router.put("/operator/policy")
async def put_policy(body: operator.OperatorPolicy, db: DB, auth: Auth) -> dict[str, Any]:
    names = [a.name.lower() for a in body.apps]
    if len(names) != len(set(names)):
        bad_request("Two apps have the same name.", code="duplicate_app")
    audit.record(
        db,
        "operator.policy_changed",
        user_id=auth.user.id,
        enabled=body.enabled,
        apps=len(body.apps),
        folders=len(body.folders),
        browser=body.browser,
        screen=body.screen,
        claude_code=body.claude_code,
        paused=body.paused,
    )
    await operator.save_policy(db, auth.user.id, body)
    return await _policy_out(db, auth.user.id)


@router.post("/operator/stop")
async def stop(db: DB, auth: Auth) -> dict[str, Any]:
    audit.record(db, "operator.kill_switch", user_id=auth.user.id)
    await operator.stop_all(db, auth.user.id)
    return await _policy_out(db, auth.user.id)


@router.post("/operator/resume")
async def resume(db: DB, auth: Auth) -> dict[str, Any]:
    policy = await operator.get_policy(db, auth.user.id)
    policy.paused = False
    audit.record(db, "operator.resumed", user_id=auth.user.id)
    await operator.save_policy(db, auth.user.id, policy)
    return await _policy_out(db, auth.user.id)


def _activity_out(e: ToolExecution, tool: Tool | None) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "tool": e.tool_name,
        "risk": e.risk,
        "status": e.status,
        "summary": _summary(tool, e.input),
        "input": e.input,
        "error": e.error,
        "output": _trim(e.output),
        "run_id": str(e.run_id) if e.run_id else None,
        "created_at": e.created_at.isoformat(),
        "finished_at": e.finished_at.isoformat() if e.finished_at else None,
    }


def _summary(tool: Tool | None, raw: dict[str, Any]) -> str:
    if tool is None:
        return ""
    try:
        return tool.summary(tool.input_model.model_validate(raw))
    except ValueError:
        return tool.name


def _trim(output: dict[str, Any] | None) -> dict[str, Any] | None:
    if output is None:
        return None
    out = {}
    for k, v in output.items():
        if isinstance(v, str) and len(v) > 600:
            v = v[:600] + "…"
        out[k] = v
    return out


@router.get("/operator/activity")
async def activity(db: DB, auth: Auth, limit: int = 50) -> list[dict[str, Any]]:
    from app.ai.tools.builtin import get_registry

    registry = get_registry()
    rows = await db.scalars(
        select(ToolExecution)
        .where(ToolExecution.user_id == auth.user.id, ToolExecution.tool_name.in_(ACTIVITY_TOOLS))
        .order_by(ToolExecution.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    return [_activity_out(e, registry.get(e.tool_name)) for e in rows]


# --- research ---------------------------------------------------------------------


class ResearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=5, max_length=1000)
    cloud: bool = False


def report_out(r: ResearchReport) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "question": r.question,
        "status": r.status,
        "cloud": r.cloud,
        "summary": r.summary,
        "findings": r.findings,
        "sources": r.sources,
        "queries": r.queries,
        "error": r.error,
        "created_at": r.created_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


@router.post("/research", status_code=status.HTTP_202_ACCEPTED)
async def start_research(body: ResearchIn, db: DB, auth: Auth) -> dict[str, Any]:
    report = await research.start(db, auth.user.id, body.question, body.cloud)
    await db.commit()
    await jobs.enqueue("research_job", report_id=str(report.id))
    await db.refresh(report)
    return report_out(report)


@router.get("/research")
async def list_research(db: DB, auth: Auth) -> list[dict[str, Any]]:
    return [report_out(r) for r in await research.recent(db, auth.user.id)]


async def _report(db: DB, auth: Auth, report_id: uuid.UUID) -> ResearchReport:
    try:
        return await research.get_owned(db, auth.user.id, report_id)
    except LookupError:
        not_found("Report not found.")


@router.get("/research/{report_id}")
async def get_research(report_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    return report_out(await _report(db, auth, report_id))


@router.delete("/research/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research(report_id: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _report(db, auth, report_id))
    await db.commit()


# --- GitHub -----------------------------------------------------------------------


@router.get("/integrations/github")
async def github_status(auth: Auth) -> dict[str, Any]:
    return {"configured": github.ready(), "repos": github.allowed_repos()}


@router.post("/integrations/github/test")
async def github_test(db: DB, auth: Auth) -> dict[str, Any]:
    """Real call to GitHub. Connected only if it answers."""
    if not github.ready():
        return {"configured": False, "connected": False, "repos": [], "error": None}
    try:
        result = await github.test()
    except github.GitHubError as exc:
        return {"configured": True, "connected": False, "repos": [], "error": str(exc)}
    audit.record(db, "integrations.github_test", user_id=auth.user.id, login=result["login"])
    await db.commit()
    return {"configured": True, "connected": True, **result, "error": None}
