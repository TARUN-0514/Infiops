"""Turn a plain sentence into a draft workflow with the local model. The draft is only
shown in the builder; nothing is saved or run until the owner saves it."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.ai.tools.registry import ToolRegistry
from app.ai.types import BudgetExceededError, ModelRequest, ModelUnavailableError
from app.models import User
from app.services.automation import CONDITION_OPS, EVENTS, WorkflowIn

DRAFT_SYSTEM = """You turn Tarun's request into an automation workflow for NEXUS. Reply with one
JSON object only, no prose:
{{"name": str, "description": str, "trigger": TRIGGER, "steps": [STEP, ...]}}

TRIGGER is one of:
- {{"type": "manual"}}
- {{"type": "schedule", "every": "day", "at": "HH:MM", "weekdays": [...]}}
  (weekdays 0-6 with Monday as 0; [] means every day)
- {{"type": "schedule", "every": "month", "day": 1-31, "at": "HH:MM"}}
- {{"type": "schedule", "every": "hours", "hours": N}}
- {{"type": "event", "event": EVENT, "filter": {{field: text}}}}
EVENTS: {events}

STEP is {{"kind": KIND, "name": short label, "config": {{...}}}} where KIND is:
- "tool": {{"tool": tool name, "args": {{...}}}}
- "agent": {{"prompt": what to write}} (the local model writes text from earlier results)
- "condition": {{"left": value, "op": one of {ops}, "right": value}}; stops the run when false
- "approval": {{"message": what to confirm}}; waits for Tarun's go-ahead
- "notify": {{"title": text, "body": text}}; sends Tarun a notification
Values can use {{{{trigger.FIELD}}}}, {{{{steps.N.output.FIELD}}}} (N counts from 1), and
{{{{now.date}}}}. An agent step's output is {{{{steps.N.output.text}}}}.

Tools you may use (name, risk, what it does):
{tools}

Use only these tools and only the inputs they take. Put an "approval" step before anything
that sends, deletes or changes something outside NEXUS. Keep it short: 1 to 6 steps."""


def _catalogue(registry: ToolRegistry) -> str:
    lines = []
    for t in registry.all():
        if t.risk == "forbidden":
            continue
        props = t.input_model.model_json_schema().get("properties", {})
        lines.append(f"- {t.name} ({t.risk}): {t.description} Inputs: {', '.join(props) or 'none'}")
    return "\n".join(lines)


def _json(text: str) -> dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON")
    out = json.loads(text[start : end + 1])
    if not isinstance(out, dict):
        raise ValueError("not an object")
    return out


def check_tools(registry: ToolRegistry, wf: WorkflowIn) -> None:
    for i, s in enumerate(wf.steps, start=1):
        if s.kind != "tool":
            continue
        tool = registry.get(str(s.config.get("tool")))
        if tool is None:
            raise ValueError(f"Step {i}: there is no tool called {s.config.get('tool')}.")
        if tool.risk == "forbidden":
            raise ValueError(f"Step {i}: {tool.name} can never run.")


async def draft(
    db: AsyncSession, gateway: ModelGateway, registry: ToolRegistry, user: User, prompt: str
) -> dict[str, Any]:
    system = DRAFT_SYSTEM.format(
        events=", ".join(
            f"{k} ({v['label']}; filter by {', '.join(v['fields'])})" for k, v in EVENTS.items()
        ),
        ops=", ".join(CONDITION_OPS),
        tools=_catalogue(registry),
    )
    try:
        resp = await gateway.complete(
            db,
            job="plan",
            req=ModelRequest(
                model="",
                system=[{"type": "text", "text": system}],
                messages=[{"role": "user", "content": f"Time zone: {user.timezone}\n\n{prompt}"}],
                max_tokens=2500,
            ),
            user_id=user.id,
        )
    except (ModelUnavailableError, BudgetExceededError) as exc:
        raise ValueError("The local model isn't reachable, so build it by hand for now.") from exc
    try:
        wf = WorkflowIn.model_validate({**_json(resp.text), "created_from_prompt": prompt})
        check_tools(registry, wf)
    except (ValueError, ValidationError) as exc:
        detail = (
            exc.errors(include_url=False)[0]["msg"]
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        raise ValueError(
            f"The model's draft didn't fit ({detail}). "
            "Try saying it differently, or build it by hand."
        ) from exc
    return wf.model_dump()
