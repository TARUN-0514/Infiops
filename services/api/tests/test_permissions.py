from httpx import AsyncClient

from app.ai.tools.builtin import get_registry
from app.ai.tools.registry import clamp
from tests.conftest import auth_headers

API = "/api/v1"


def test_clamp_hard_limits() -> None:
    assert clamp("read", None) == "allow"
    assert clamp("sensitive", None) == "ask"
    assert clamp("sensitive", "allow") == "allow"  # owner may relax sensitive tools
    assert clamp("irreversible", "allow") == "ask"  # but never irreversible ones
    assert clamp("forbidden", "allow") == "deny"
    assert clamp("reversible", "deny") == "deny"


def test_every_tool_has_a_risk_and_a_valid_schema() -> None:
    for tool in get_registry().all():
        spec = tool.spec()
        assert spec.input_schema["type"] == "object"
        assert tool.risk in {
            "read",
            "draft",
            "reversible",
            "sensitive",
            "irreversible",
            "forbidden",
        }


async def test_permission_api(client: AsyncClient) -> None:
    h = await auth_headers(client)
    tools = (await client.get(f"{API}/tools", headers=h)).json()
    delete = next(t for t in tools if t["name"] == "tasks_delete")
    assert delete["effective"] == "ask"
    r = await client.put(
        f"{API}/tools/tasks_delete/permission", json={"decision": "deny"}, headers=h
    )
    assert r.json()["effective"] == "deny"
    r = await client.put(
        f"{API}/tools/tasks_delete/permission", json={"decision": "default"}, headers=h
    )
    assert r.json()["effective"] == "ask"
    assert (
        await client.put(f"{API}/tools/nope/permission", json={"decision": "deny"}, headers=h)
    ).status_code == 404
    assert (await client.get(f"{API}/tools")).status_code == 401
