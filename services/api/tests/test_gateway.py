import json

import httpx
import pytest
from sqlalchemy import select

from app.ai.gateway import ModelGateway
from app.ai.providers import LocalProvider, ScriptedProvider, _ThinkFilter
from app.ai.types import (
    BudgetExceededError,
    ModelRequest,
    ModelUnavailableError,
    ToolSpec,
)
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import ModelUsageLog


def _gw(**overrides: object) -> tuple[ModelGateway, ScriptedProvider, ScriptedProvider]:
    local, cloud = ScriptedProvider("local"), ScriptedProvider("anthropic")
    settings = get_settings().model_copy(update=overrides)
    return ModelGateway(settings, {"local": local, "anthropic": cloud}), local, cloud


def _req() -> ModelRequest:
    return ModelRequest(
        model="",
        system=[{"type": "text", "text": "s"}],
        messages=[{"role": "user", "content": "hi"}],
    )


async def test_local_is_the_default_and_usage_is_logged() -> None:
    gw, local, cloud = _gw()
    async with get_sessionmaker()() as db:
        resp = await gw.complete(db, job="chat", req=_req(), user_id=None)
        await db.commit()
        rows = list(await db.scalars(select(ModelUsageLog)))
    assert resp.provider == "local" and len(local.requests) == 1 and not cloud.requests
    assert resp.model == get_settings().local_model
    assert rows[0].provider == "local" and rows[0].cost_usd is None  # no invented prices


async def test_cloud_is_off_by_default() -> None:
    gw, _, _ = _gw()
    async with get_sessionmaker()() as db:
        with pytest.raises(ModelUnavailableError, match="Cloud is off"):
            await gw.complete(db, job="chat", req=_req(), user_id=None, cloud=True)


async def test_cloud_when_enabled_and_secret_stays_local() -> None:
    gw, local, cloud = _gw(cloud_enabled=True)
    async with get_sessionmaker()() as db:
        r1 = await gw.complete(db, job="plan", req=_req(), user_id=None, cloud=True)
        r2 = await gw.complete(
            db, job="chat", req=_req(), user_id=None, cloud=True, privacy="secret"
        )
    assert r1.provider == "anthropic" and r1.model == get_settings().cloud_model_plan
    assert r2.provider == "local"
    assert len(cloud.requests) == 1 and len(local.requests) == 1


async def test_cloud_daily_cap() -> None:
    gw, _, _ = _gw(cloud_enabled=True, cloud_daily_token_budget=20)
    async with get_sessionmaker()() as db:
        await gw.complete(db, job="chat", req=_req(), user_id=None, cloud=True)  # 15 tokens
        await gw.complete(db, job="chat", req=_req(), user_id=None, cloud=True)  # 30
        with pytest.raises(BudgetExceededError):
            await gw.complete(db, job="chat", req=_req(), user_id=None, cloud=True)
        # the local model keeps working with no cap
        assert (await gw.complete(db, job="chat", req=_req(), user_id=None)).provider == "local"


async def test_unreachable_local_model_is_reported_plainly() -> None:
    local = ScriptedProvider("local")
    local.push(httpx.ConnectError("refused"))
    gw = ModelGateway(get_settings(), {"local": local})
    async with get_sessionmaker()() as db:
        with pytest.raises(ModelUnavailableError, match="Start Ollama or LM Studio"):
            await gw.complete(db, job="chat", req=_req(), user_id=None)


def test_think_filter_hides_reasoning_split_across_chunks() -> None:
    f = _ThinkFilter()
    out = "".join(f.feed(c) for c in ["<thi", "nk>secret plan</th", "ink>Hello ", "there"])
    assert out + f.flush() == "Hello there"


def _sse(chunks: list[dict[str, object]]) -> bytes:
    lines = [f"data: {json.dumps(c)}" for c in chunks] + ["data: [DONE]"]
    return ("\n\n".join(lines) + "\n\n").encode()


async def test_local_provider_streams_text_and_assembles_tool_calls() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            content=_sse(
                [
                    {"choices": [{"delta": {"content": "Sure. "}}]},
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_1",
                                            "function": {
                                                "name": "tasks_create",
                                                "arguments": '{"title": "Bu',
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {"index": 0, "function": {"arguments": 'y milk"}'}}
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                    {"choices": [], "usage": {"prompt_tokens": 30, "completion_tokens": 9}},
                ]
            ),
        )

    provider = LocalProvider("http://local/v1", True, transport=httpx.MockTransport(handler))
    seen: list[str] = []

    async def on_text(t: str) -> None:
        seen.append(t)

    req = ModelRequest(
        model="qwen3:14b",
        system=[{"type": "text", "text": "sys"}],
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "add milk"}]},
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t0", "name": "time_now", "input": {}}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t0", "content": '{"now": "x"}'}
                ],
            },
        ],
        tools=[ToolSpec("tasks_create", "Create", {"type": "object", "properties": {}})],
    )
    resp = await provider.complete(req, on_text)
    assert "".join(seen) == "Sure. "
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls[0].name == "tasks_create"
    assert resp.tool_calls[0].input == {"title": "Buy milk"}
    assert resp.input_tokens == 30 and resp.output_tokens == 9
    msgs = captured["messages"]
    assert isinstance(msgs, list)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[2]["tool_calls"][0]["function"]["name"] == "time_now"
    assert msgs[3]["tool_call_id"] == "t0"
    assert captured["tools"][0]["function"]["name"] == "tasks_create"  # type: ignore[index]
