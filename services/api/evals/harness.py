"""Agent evals: does the assistant pick the right tools, and only those, for real requests?

Each scenario in scenarios.json gives a request, optional setup data, what must and must
not happen, and a recorded model response. `run_scenario` drives the real API (chat,
tools, permission checks, approvals) through an HTTP client, so a scenario passes only if
the whole path behaves, not just the model's text.

Two ways to run:
- recorded: the model is replaced by the recorded response. Runs in CI as a regression
  test of everything around the model (tests/test_agent_evals.py).
- live: the owner's local model answers (python -m evals.run). This is the real eval of
  the model's tool choice; --record saves its answers back as the new recordings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from httpx import AsyncClient

API = "/api/v1"
SCENARIOS = Path(__file__).with_name("scenarios.json")
WRITE_TOOLS_HINT = (
    "create",
    "update",
    "delete",
    "complete",
    "send",
    "add",
    "log",
    "tick",
    "forget",
    "remember",
    "write",
    "move",
    "act",
)


def load() -> list[dict[str, Any]]:
    return list(json.loads(SCENARIOS.read_text()))


@dataclass
class Result:
    id: str
    passed: bool
    calls: list[str]
    approvals: int
    reply: str
    problems: list[str] = field(default_factory=list)
    responses: list[Any] = field(default_factory=list)  # filled when recording


async def setup(client: AsyncClient, h: dict[str, str], sc: dict[str, Any]) -> dict[str, str]:
    """Create the scenario's starting data. Returns placeholders like {"task:Gym": id}."""
    refs: dict[str, str] = {}
    s = sc.get("setup", {})
    for title in s.get("tasks", []):
        r = await client.post(f"{API}/tasks", json={"title": title}, headers=h)
        r.raise_for_status()
        refs[f"task:{title}"] = r.json()["id"]
    for name in s.get("habits", []):
        r = await client.post(f"{API}/habits", json={"name": name}, headers=h)
        r.raise_for_status()
        refs[f"habit:{name}"] = r.json()["id"]
    return refs


def fill(value: Any, refs: dict[str, str]) -> Any:
    """Replace {{task:Title}} placeholders in recorded inputs with this run's ids."""
    if isinstance(value, str):
        return re.sub(r"\{\{([^}]+)\}\}", lambda m: refs.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [fill(v, refs) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, refs) for k, v in value.items()}
    return value


def _args_match(want: dict[str, Any], got: dict[str, Any]) -> list[str]:
    problems = []
    for key, expected in want.items():
        if key.endswith("~"):
            name = key[:-1]
            if str(expected).lower() not in str(got.get(name, "")).lower():
                problems.append(f"{name}={got.get(name)!r} should contain {expected!r}")
        elif got.get(key) != expected:
            problems.append(f"{key}={got.get(key)!r}, expected {expected!r}")
    return problems


def score(
    sc: dict[str, Any],
    events: list[dict[str, Any]],
    refs: dict[str, str],
    inputs: dict[str, dict[str, Any]],
) -> Result:
    """inputs: the first input the model gave each tool, from the saved conversation."""
    expect = sc["expect"]
    calls = [e["name"] for e in events if e["type"] == "tool.started"]
    approvals = sum(e["type"] == "approval.required" for e in events)
    done = [e for e in events if e["type"] == "message.completed"]
    reply = done[-1]["message"]["text"] if done else ""
    problems: list[str] = []
    for name in expect.get("calls", []):
        if name not in calls:
            problems.append(f"didn't call {name}")
    any_of = expect.get("any_of")
    if any_of and not set(any_of) & set(calls):
        problems.append(f"called none of {any_of}")
    for name in expect.get("never", []):
        if name in calls:
            problems.append(f"called {name}, which it must not")
    if expect.get("no_writes") and any(any(w in c for w in WRITE_TOOLS_HINT) for c in calls):
        problems.append(f"changed something when it shouldn't have: {calls}")
    if "approvals" in expect and approvals != expect["approvals"]:
        problems.append(f"{approvals} approval requests, expected {expect['approvals']}")
    for name, want in fill(expect.get("args", {}), refs).items():
        got = inputs.get(name)
        if got is None:
            continue  # already reported as a missing call
        problems += [f"{name}: {p}" for p in _args_match(want, got)]
    for text in expect.get("reply~", []):
        if text.lower() not in reply.lower():
            problems.append(f"reply should mention {text!r}")
    return Result(sc["id"], not problems, calls, approvals, reply, problems)


async def run_scenario(
    client: AsyncClient, h: dict[str, str], sc: dict[str, Any], push: Any = None
) -> Result:
    """push: in recorded mode, a callable that queues the recorded responses."""
    refs = await setup(client, h, sc)
    if push is not None:
        push(*fill(sc["recorded"], refs))
    cid = (await client.post(f"{API}/chat/conversations", headers=h)).json()["id"]
    r = await client.post(
        f"{API}/chat/conversations/{cid}/messages", json={"text": sc["prompt"]}, headers=h
    )
    r.raise_for_status()
    events = [json.loads(line) for line in r.text.splitlines() if line]
    conv = (await client.get(f"{API}/chat/conversations/{cid}", headers=h)).json()
    inputs: dict[str, dict[str, Any]] = {}
    for m in conv["messages"]:
        for t in m.get("tools", []):
            inputs.setdefault(t["name"], t["input"])
    return score(sc, events, refs, inputs)
