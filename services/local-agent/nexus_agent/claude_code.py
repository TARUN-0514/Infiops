"""Claude Code runs on this PC, in a project folder the owner allowed. Plan-only unless the
request allows edits; Claude Code's own permission rules still apply, and in print mode it
cannot run commands that need approval."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
from typing import Any

from nexus_agent.operator import Operator, Refused

TIMEOUT = 840.0


def available() -> bool:
    return shutil.which("claude") is not None


class ClaudeCode:
    def __init__(self, op: Operator) -> None:
        self.op = op
        self.procs: set[asyncio.subprocess.Process] = set()

    async def run(self, a: dict[str, Any]) -> dict[str, Any]:
        self.op.check("claude_code")
        edits = bool(a.get("allow_edits"))
        cwd = self.op.folder(str(a.get("cwd", "")), write=edits)
        if not cwd.is_dir():
            raise Refused("That isn't a folder.")
        exe = shutil.which("claude")
        if exe is None:
            raise Refused(
                "Claude Code isn't installed on this PC (npm i -g @anthropic-ai/claude-code)."
            )
        prompt = str(a.get("prompt", ""))[:8000]
        argv = [
            exe,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits" if edits else "plan",
        ]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.procs.add(proc)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
        except (TimeoutError, asyncio.CancelledError):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            raise
        finally:
            self.procs.discard(proc)
        if proc.returncode != 0 and not out:
            raise Refused(f"Claude Code stopped: {err.decode(errors='replace')[-400:].strip()}")
        try:
            data = json.loads(out)
        except ValueError:
            return {"result": out.decode(errors="replace")[-12000:], "edits": edits}
        return {
            "result": str(data.get("result", ""))[-12000:],
            "is_error": bool(data.get("is_error")),
            "turns": data.get("num_turns"),
            "cost_usd": data.get("total_cost_usd"),
            "session_id": data.get("session_id"),
            "edits": edits,
            "folder": str(cwd),
        }

    async def kill_all(self) -> None:
        for proc in list(self.procs):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()


def install(op: Operator) -> ClaudeCode:
    cc = ClaudeCode(op)
    op.extra["claude_code"] = cc.run
    op.on_stop.append(cc.kill_all)
    return cc
