"""Agent evals replayed from recorded model responses (see evals/harness.py).

These check everything around the model for each scenario: the right tool runs with the
right input, sensitive ones wait for approval, and injected instructions change nothing.
The live version, against the owner's local model, is `python -m evals.run`."""

import pytest
from httpx import AsyncClient

from app.ai.providers import ScriptedProvider
from evals import harness
from tests.conftest import auth_headers

SCENARIOS = harness.load()


def test_scenarios_are_well_formed() -> None:
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) >= 10
    for s in SCENARIOS:
        assert {"id", "prompt", "expect", "recorded"} <= set(s), s["id"]


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
async def test_recorded_scenario(
    sc: dict[str, object], client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    result = await harness.run_scenario(client, h, sc, push=model.push)  # type: ignore[arg-type]
    assert result.passed, result.problems


def test_scoring_catches_a_bad_answer() -> None:
    sc = {
        "id": "x",
        "expect": {"calls": ["tasks_create"], "never": ["tasks_delete"], "approvals": 0},
    }
    events = [
        {"type": "tool.started", "name": "tasks_delete"},
        {"type": "approval.required", "approval": {"tool_name": "tasks_delete", "input": {}}},
    ]
    r = harness.score(sc, events, {}, {})
    assert not r.passed
    assert r.problems == [
        "didn't call tasks_create",
        "called tasks_delete, which it must not",
        "1 approval requests, expected 0",
    ]
