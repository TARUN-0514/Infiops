"""Tool registry and permission engine. Every tool declares a risk level; the server,
not the model, decides whether a call runs, waits for approval, or is refused."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ToolSpec
from app.models import PermissionPolicy, User

Risk = Literal["read", "draft", "reversible", "sensitive", "irreversible", "forbidden"]
Decision = Literal["allow", "ask", "deny"]

DEFAULT_DECISION: dict[str, Decision] = {
    "read": "allow",
    "draft": "allow",
    "reversible": "allow",
    "sensitive": "ask",
    "irreversible": "ask",
    "forbidden": "deny",
}


@dataclass
class ToolContext:
    db: AsyncSession
    user: User
    run_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None


Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    risk: Risk
    input_model: type[BaseModel]
    handler: Handler
    summary: Callable[[Any], str]  # one line shown on approval cards
    # Runs when the owner declines the call, to undo any "waiting" state the
    # request set up (for example a draft marked as waiting for approval).
    on_reject: Callable[[ToolContext, Any], Awaitable[None]] | None = None

    def spec(self) -> ToolSpec:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return ToolSpec(self.name, self.description, schema)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def specs(self, exclude_risks: set[str] | None = None) -> list[ToolSpec]:
        return [
            t.spec()
            for t in self.all()
            if t.risk != "forbidden" and t.risk not in (exclude_risks or set())
        ]


def clamp(risk: Risk, policy: Decision | None) -> Decision:
    """Apply a user policy within hard limits: forbidden is always denied and
    irreversible can never run without asking."""
    if risk == "forbidden":
        return "deny"
    decision = policy or DEFAULT_DECISION[risk]
    if risk == "irreversible" and decision == "allow":
        return "ask"
    return decision


async def policies(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Decision]:
    rows = await db.scalars(select(PermissionPolicy).where(PermissionPolicy.user_id == user_id))
    return {p.tool_name: p.decision for p in rows}  # type: ignore[misc]


async def decide(db: AsyncSession, user_id: uuid.UUID, tool: Tool) -> Decision:
    policy = await db.scalar(
        select(PermissionPolicy.decision).where(
            PermissionPolicy.user_id == user_id, PermissionPolicy.tool_name == tool.name
        )
    )
    return clamp(tool.risk, policy)  # type: ignore[arg-type]
