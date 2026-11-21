"""Computer control on the PC: the agent's own checks, with the real file system."""

import asyncio
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from nexus_agent import claude_code
from nexus_agent.config import AgentConfig
from nexus_agent.operator import Operator
from nexus_agent.runtime import Agent
from nexus_agent.screen import Screen
from tests.test_api_and_voice import FakeServer, make_api


@pytest.fixture
def docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("NEXUS_AGENT_HOME", str(tmp_path / "agent-home"))
    root = tmp_path / "docs"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "plan.md").write_text("# Plan\nShip phase 4.\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("hunter2", encoding="utf-8")
    (tmp_path / "pics").mkdir()
    return root


def _op(docs: Path, **policy: Any) -> Operator:
    op = Operator(control=True)
    op.set_policy(
        {
            "enabled": True,
            "folders": [{"path": str(docs), "write": True}, {"path": str(docs.parent / "pics")}],
            "apps": [{"name": "Python", "command": f'"{sys.executable}" -c "pass"'}],
            **policy,
        }
    )
    return op


async def _call(op: Operator, tool: str, **args: Any) -> dict[str, Any]:
    return await op.handle_call({"id": "c1", "tool": tool, "input": args})


async def test_nothing_runs_until_control_is_on_here_and_in_nexus(docs: Path) -> None:
    off_here = Operator(control=False)
    off_here.set_policy({"enabled": True, "folders": [{"path": str(docs), "write": True}]})
    r = await _call(off_here, "files_list", path=str(docs))
    assert r["ok"] is False and "nexus-agent control on" in r["error"]

    no_policy = Operator(control=True)  # policy not received yet: deny
    r = await _call(no_policy, "files_list", path=str(docs))
    assert r["ok"] is False and "off in NEXUS" in r["error"]


async def test_files_inside_the_allowed_folder(docs: Path) -> None:
    op = _op(docs)
    r = await _call(op, "files_list", path=str(docs))
    assert r["ok"], r
    assert [e["name"] for e in r["output"]["entries"]] == ["notes"]
    r = await _call(op, "files_read", path=str(docs / "notes" / "plan.md"))
    assert r["output"]["text"].startswith("# Plan")

    target = docs / "notes" / "new.md"
    r = await _call(op, "files_write", path=str(target), content="hello")
    assert r["ok"] and target.read_text() == "hello"
    r = await _call(op, "files_write", path=str(target), content="again")
    assert not r["ok"] and "already exists" in r["error"]
    r = await _call(op, "files_write", path=str(target), content="again", overwrite=True)
    assert r["ok"] and target.read_text() == "again"

    r = await _call(op, "files_move", source=str(target), destination=str(docs / "moved.md"))
    assert r["ok"] and (docs / "moved.md").exists() and not target.exists()
    r = await _call(
        op, "files_move", source=str(docs / "moved.md"), destination=str(docs / "notes" / "plan.md")
    )
    assert not r["ok"] and "won't replace" in r["error"]
    assert op.history[-1]["tool"] == "files_move" and op.history[-1]["ok"] is False


async def test_escapes_are_refused(docs: Path, tmp_path: Path) -> None:
    op = _op(docs)
    r = await _call(op, "files_read", path=str(docs / ".." / "secret.txt"))
    assert not r["ok"] and "isn't in an allowed folder" in r["error"]
    r = await _call(op, "files_read", path="notes/plan.md")
    assert not r["ok"] and "full path" in r["error"]

    link = docs / "sneaky.txt"
    link.symlink_to(tmp_path / "secret.txt")
    r = await _call(op, "files_read", path=str(link))
    assert not r["ok"] and "link that leads outside" in r["error"]

    r = await _call(op, "files_write", path=str(tmp_path / "pics" / "x.txt"), content="x")
    assert not r["ok"] and "read-only" in r["error"]

    # The agent's own folder (pairing token) is off limits even if the policy allows it.
    home = Path(os.environ["NEXUS_AGENT_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "agent.json").write_text("{}")
    op.set_policy({"enabled": True, "folders": [{"path": str(tmp_path), "write": True}]})
    r = await _call(op, "files_read", path=str(home / "agent.json"))
    assert not r["ok"] and "system or credential" in r["error"]

    r = await _call(op, "files_read", path=str(tmp_path / "docs" / "notes"))
    assert not r["ok"] and "isn't a file" in r["error"]


async def test_binary_files_are_not_read(docs: Path) -> None:
    (docs / "a.exe").write_bytes(b"MZ\x00")
    r = await _call(_op(docs), "files_read", path=str(docs / "a.exe"))
    assert not r["ok"] and "text files" in r["error"]


async def test_apps_must_match_exactly(docs: Path) -> None:
    op = _op(docs)
    allowed = op.policy.apps[0]
    r = await _call(op, "open_app", **allowed)
    assert r["ok"] and r["output"] == {"started": "Python"}
    r = await _call(op, "open_app", name="Python", command="rm -rf /")
    assert not r["ok"] and "isn't an allowed app" in r["error"]
    r = await _call(op, "open_url", url="file:///etc/passwd")
    assert not r["ok"]


async def test_paused_and_unknown_tools(docs: Path) -> None:
    op = _op(docs, paused=True)
    r = await _call(op, "files_list", path=str(docs))
    assert not r["ok"] and "paused" in r["error"]
    r = await _call(_op(docs), "format_disk")
    assert not r["ok"] and "can't do format_disk" in r["error"]
    r = await _call(_op(docs), "screen", action="screenshot")
    assert not r["ok"]  # screen module not installed in this operator


async def test_stop_cancels_running_actions(docs: Path) -> None:
    op = _op(docs)
    started = asyncio.Event()

    async def slow(_: dict[str, Any]) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(30)
        return {}

    op.extra["slow"] = slow
    task = asyncio.create_task(_call(op, "slow"))
    await started.wait()
    await op.stop()
    r = await asyncio.wait_for(task, 2)
    assert r == {"type": "result", "id": "c1", "ok": False, "error": "Stopped."}
    assert op.policy.paused is True


# --- screen ---------------------------------------------------------------------------


class FakeImage:
    def __init__(self, w: int, h: int) -> None:
        self.width, self.height = w, h

    def resize(self, size: tuple[int, int]) -> "FakeImage":
        return FakeImage(*size)

    def save(self, buf: Any, format: str, optimize: bool) -> None:
        buf.write(b"\x89PNG")


class FakeGui:
    def __init__(self) -> None:
        self.log: list[tuple[Any, ...]] = []

    def size(self) -> tuple[int, int]:
        return (2560, 1600)

    def screenshot(self) -> FakeImage:
        return FakeImage(2560, 1600)

    def __getattr__(self, name: str) -> Any:
        return lambda *a, **k: self.log.append((name, a, k))


async def test_screen_scales_and_refuses(docs: Path) -> None:
    op = _op(docs, screen=True)
    gui = FakeGui()
    s = Screen(op, gui)
    op.extra["screen"] = s.act
    r = await _call(op, "screen", action="screenshot")
    assert r["ok"] and r["output"]["width"] == 1280 and r["output"]["height"] == 800
    r = await _call(op, "screen", action="left_click", coordinate=[640, 400])
    assert r["ok"] and gui.log[0] == ("moveTo", (1280, 800), {})
    assert gui.log[1][0] == "click"
    r = await _call(op, "screen", action="key", text="ctrl+alt+del")
    assert not r["ok"] and "won't press" in r["error"]
    r = await _call(op, "screen", action="left_click", coordinate=[5000, 1])
    assert not r["ok"] and "off the screen" in r["error"]
    r = await _call(op, "screen", action="key", text="Return")
    assert r["ok"] and gui.log[-1] == ("hotkey", ("enter",), {})

    op.set_policy({"enabled": True, "screen": False})
    r = await _call(op, "screen", action="screenshot")
    assert not r["ok"] and "Screen is off" in r["error"]


# --- Claude Code ---------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="uses a shell script as a fake claude")
async def test_claude_code_runs_plan_only_in_allowed_folder(
    docs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text(
        "#!/bin/sh\n"
        'printf \'{"result":"%s in %s","num_turns":2,"total_cost_usd":0.01,"session_id":"s1"}\' '
        '"$*" "$(pwd)"\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert claude_code.available()

    op = _op(docs, claude_code=True)
    claude_code.install(op)
    r = await _call(op, "claude_code", cwd=str(docs), prompt="explain this repo")
    assert r["ok"], r
    out = r["output"]
    assert "--permission-mode plan" in out["result"] and str(docs) in out["result"]
    assert out["turns"] == 2 and out["edits"] is False

    r = await _call(
        op, "claude_code", cwd=str(tmp_path / "pics"), prompt="fix it", allow_edits=True
    )
    assert not r["ok"] and "read-only" in r["error"]

    op.set_policy({**json.loads(json.dumps(op.policy.__dict__)), "claude_code": False})
    r = await _call(op, "claude_code", cwd=str(docs), prompt="explain")
    assert not r["ok"] and "Claude code is off" in r["error"]


# --- through the agent's socket handler ------------------------------------------------


async def test_agent_answers_calls_and_reports_capabilities(
    docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = FakeServer()
    api = make_api(server)
    api.config.control = True
    agent = Agent(api, None, None)
    sent: list[dict[str, Any]] = []

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    monkeypatch.setattr(agent, "send", send)
    assert agent.capabilities()["operator"] is True
    await agent.handle(
        {"type": "policy", "policy": {"enabled": True, "folders": [{"path": str(docs)}]}}
    )
    await agent.handle(
        {"type": "call", "id": "a" * 32, "tool": "files_list", "input": {"path": str(docs)}}
    )
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.02)
    assert sent[0]["type"] == "result" and sent[0]["ok"] is True and sent[0]["id"] == "a" * 32

    # Voice "stop listening" doesn't pause computer control; the kill switch does.
    await agent.handle({"type": "stop"})
    assert agent.operator.policy.paused is False
    await agent.handle({"type": "stop", "scope": "all"})
    assert agent.operator.policy.paused is True

    assert Agent(make_api(server), None, None).capabilities()["operator"] is False
    assert AgentConfig().control is False
