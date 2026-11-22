"""Automations: workflows, their runs, checkpoints, and drafts from plain language."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.ai.gateway import get_gateway
from app.ai.tools.builtin import get_registry
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import AutomationRun, AutomationStep, AutomationWorkflow
from app.services import audit, automation_draft, automation_engine
from app.services import automation as au

router = APIRouter(tags=["automations"])


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def run_out(r: AutomationRun, name: str | None = None) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "workflow_id": str(r.workflow_id),
        "workflow": name,
        "status": r.status,
        "trigger": r.trigger,
        "cursor": r.cursor,
        "steps": [
            {k: v for k, v in s.items() if k != "config"} | {"config": s.get("config")}
            for s in r.steps
        ],
        "error": r.error,
        "resume_at": r.resume_at.isoformat() if r.resume_at and r.status == "retrying" else None,
        "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def health(runs: list[AutomationRun]) -> dict[str, Any]:
    """Last 14 days, for the gate: finished runs and how many didn't fail."""
    done = [r for r in runs if r.status in ("succeeded", "stopped", "failed", "cancelled")]
    failed = sum(1 for r in done if r.status == "failed")
    return {
        "runs": len(done),
        "failed": failed,
        "success_pct": round(100 * (len(done) - failed) / len(done)) if done else None,
    }


async def wf_out(db: DB, wf: AutomationWorkflow, with_steps: bool = True) -> dict[str, Any]:
    steps = list(
        await db.scalars(
            select(AutomationStep)
            .where(AutomationStep.workflow_id == wf.id)
            .order_by(AutomationStep.ordinal)
        )
    )
    since = datetime.now(UTC) - timedelta(days=14)
    recent = list(
        await db.scalars(
            select(AutomationRun)
            .where(AutomationRun.workflow_id == wf.id, AutomationRun.started_at >= since)
            .order_by(AutomationRun.started_at.desc())
        )
    )
    return {
        "id": str(wf.id),
        "name": wf.name,
        "description": wf.description,
        "trigger": wf.trigger,
        "trigger_label": au.describe_trigger(wf.trigger),
        "enabled": wf.enabled,
        "created_from_prompt": wf.created_from_prompt,
        "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at and wf.enabled else None,
        "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
        "last_status": recent[0].status if recent else None,
        "health": health(recent),
        "steps": [
            {"kind": s.kind, "name": s.name, "config": s.config, "retry_max": s.retry_max}
            for s in steps
        ]
        if with_steps
        else [],
        "step_count": len(steps),
    }


async def _wf(db: DB, auth: Auth, wid: uuid.UUID) -> AutomationWorkflow:
    wf = await db.get(AutomationWorkflow, wid)
    if wf is None or wf.user_id != auth.user.id:
        not_found("Automation not found.")
    return wf


async def _save(db: DB, auth: Auth, wf: AutomationWorkflow, body: au.WorkflowIn) -> None:
    try:
        automation_draft.check_tools(get_registry(), body)
    except ValueError as exc:
        bad_request(str(exc))
    trigger = body.trigger.model_dump()
    wf.name, wf.description, wf.trigger, wf.enabled = (
        body.name.strip(),
        body.description,
        trigger,
        body.enabled,
    )
    if body.created_from_prompt:
        wf.created_from_prompt = body.created_from_prompt
    wf.next_run_at = au.next_run(trigger, auth.user.timezone, datetime.now(UTC))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have an automation with that name.")
    await db.execute(delete(AutomationStep).where(AutomationStep.workflow_id == wf.id))
    for i, s in enumerate(body.steps, start=1):
        db.add(
            AutomationStep(
                workflow_id=wf.id,
                ordinal=i,
                kind=s.kind,
                name=s.name.strip(),
                config=s.config,
                retry_max=s.retry_max,
            )
        )
    audit.record(
        db,
        "automation.saved",
        user_id=auth.user.id,
        target=str(wf.id),
        steps=len(body.steps),
        tools=[s.config.get("tool") for s in body.steps if s.kind == "tool"],
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have an automation with that name.")


@router.get("/automations/meta")
async def meta(auth: Auth) -> dict[str, Any]:
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "risk": t.risk,
            "local_only": t.local_only,
            "inputs": t.input_model.model_json_schema().get("properties", {}),
            "required": t.input_model.model_json_schema().get("required", []),
        }
        for t in get_registry().all()
        if t.risk != "forbidden"
    ]
    return {
        "events": [{"name": k, **v} for k, v in au.EVENTS.items()],
        "condition_ops": list(au.CONDITION_OPS),
        "tools": tools,
        "timezone": auth.user.timezone,
    }


@router.get("/automations")
async def list_workflows(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(AutomationWorkflow)
        .where(AutomationWorkflow.user_id == auth.user.id)
        .order_by(AutomationWorkflow.created_at)
    )
    return [await wf_out(db, w, with_steps=False) for w in rows]


@router.post("/automations", status_code=status.HTTP_201_CREATED)
async def create_workflow(body: au.WorkflowIn, db: DB, auth: Auth) -> dict[str, Any]:
    wf = AutomationWorkflow(user_id=auth.user.id, name=body.name, trigger={})
    db.add(wf)
    await _save(db, auth, wf, body)
    return await wf_out(db, wf)


class DraftIn(_In):
    prompt: str = Field(min_length=5, max_length=2000)


@router.post("/automations/draft")
async def draft_workflow(body: DraftIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        out = await automation_draft.draft(
            db, get_gateway(), get_registry(), auth.user, body.prompt
        )
    except ValueError as exc:
        bad_request(str(exc), code="draft_failed")
    await db.commit()  # keeps the model usage log
    return out


@router.get("/automations/{wid}")
async def get_workflow(wid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    return await wf_out(db, await _wf(db, auth, wid))


@router.put("/automations/{wid}")
async def update_workflow(
    wid: uuid.UUID, body: au.WorkflowIn, db: DB, auth: Auth
) -> dict[str, Any]:
    wf = await _wf(db, auth, wid)
    await _save(db, auth, wf, body)
    return await wf_out(db, wf)


class EnabledIn(_In):
    enabled: bool


@router.patch("/automations/{wid}")
async def set_enabled(wid: uuid.UUID, body: EnabledIn, db: DB, auth: Auth) -> dict[str, Any]:
    wf = await _wf(db, auth, wid)
    wf.enabled = body.enabled
    wf.next_run_at = (
        au.next_run(wf.trigger, auth.user.timezone, datetime.now(UTC)) if body.enabled else None
    )
    await db.commit()
    return await wf_out(db, wf)


@router.delete("/automations/{wid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(wid: uuid.UUID, db: DB, auth: Auth) -> None:
    wf = await _wf(db, auth, wid)
    audit.record(db, "automation.deleted", user_id=auth.user.id, target=str(wf.id), name=wf.name)
    await db.delete(wf)
    await db.commit()


@router.post("/automations/{wid}/run")
async def run_now(wid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    wf = await _wf(db, auth, wid)
    run = await automation_engine.start_run(db, wf, {"type": "manual", "data": {}})
    await db.commit()
    run = await automation_engine.execute(db, get_gateway(), get_registry(), run)
    return run_out(run, wf.name)


@router.get("/automation-runs")
async def list_runs(
    db: DB,
    auth: Auth,
    workflow_id: uuid.UUID | None = None,
    state: Literal["waiting", "failed", "all"] = "all",
    limit: int = Query(30, ge=1, le=100),
) -> list[dict[str, Any]]:
    stmt = (
        select(AutomationRun, AutomationWorkflow.name)
        .join(AutomationWorkflow, AutomationWorkflow.id == AutomationRun.workflow_id)
        .where(AutomationRun.user_id == auth.user.id)
    )
    if workflow_id:
        stmt = stmt.where(AutomationRun.workflow_id == workflow_id)
    if state == "waiting":
        stmt = stmt.where(AutomationRun.status == "waiting_approval")
    elif state == "failed":
        stmt = stmt.where(AutomationRun.status == "failed")
    rows = await db.execute(stmt.order_by(AutomationRun.started_at.desc()).limit(limit))
    return [run_out(r, name) for r, name in rows.tuples()]


async def _run(db: DB, auth: Auth, rid: uuid.UUID) -> tuple[AutomationRun, str]:
    run = await db.get(AutomationRun, rid)
    if run is None or run.user_id != auth.user.id:
        not_found("Run not found.")
    wf = await db.get(AutomationWorkflow, run.workflow_id)
    return run, wf.name if wf else ""


@router.get("/automation-runs/{rid}")
async def get_run(rid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    run, name = await _run(db, auth, rid)
    return run_out(run, name)


class DecideIn(_In):
    approve: bool


@router.post("/automation-runs/{rid}/decide")
async def decide_checkpoint(rid: uuid.UUID, body: DecideIn, db: DB, auth: Auth) -> dict[str, Any]:
    run, name = await _run(db, auth, rid)
    audit.record(
        db, "automation.checkpoint", user_id=auth.user.id, target=str(run.id), approve=body.approve
    )
    try:
        run = await automation_engine.decide_checkpoint(
            db, get_gateway(), get_registry(), run, body.approve
        )
    except ValueError as exc:
        bad_request(str(exc))
    return run_out(run, name)


@router.post("/automation-runs/{rid}/cancel")
async def cancel_run(rid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    run, name = await _run(db, auth, rid)
    if run.status not in ("queued", "waiting_approval", "retrying"):
        bad_request("Only a waiting or queued run can be cancelled.")
    run.status, run.finished_at, run.error = "cancelled", datetime.now(UTC), "You cancelled it."
    await db.commit()
    return run_out(run, name)
