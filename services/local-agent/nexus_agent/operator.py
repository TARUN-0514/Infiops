"""Computer control on this PC. NEXUS's server checks every action against the owner's policy;
this module checks again here, with the real file system, before doing anything:

- nothing runs unless control was switched on on this PC (`nexus-agent control on`),
- folders are resolved (links followed) and must stay inside an allowed folder,
- system and credential folders are refused whatever the policy says,
- apps must match the policy exactly and start without a shell,
- Stop cancels everything that is running."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shlex
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nexus_agent.config import config_dir

log = logging.getLogger("nexus.operator")

TEXT_TYPES = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".log",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".css",
    ".xml",
    ".sql",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".sh",
    ".ps1",
    ".bat",
}
MAX_LIST = 500
MAX_WRITE = 200_000


class Refused(Exception):
    """The PC won't do this; the message goes back to NEXUS."""


def _norm(p: Path) -> str:
    return os.path.normcase(str(p))


def _blocked_roots() -> list[Path]:
    home = Path.home()
    roots = [config_dir(), home / ".ssh", home / ".aws", home / ".gnupg", home / ".config" / "gh"]
    if sys.platform == "win32":
        env = os.environ
        roots += [
            Path(env.get("SystemRoot", "C:\\Windows")),
            Path(env.get("ProgramFiles", "C:\\Program Files")),
            Path(env.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
            Path(env.get("ProgramData", "C:\\ProgramData")),
            Path(env.get("LOCALAPPDATA", str(home / "AppData" / "Local"))) / "Microsoft",
            Path(env.get("APPDATA", str(home / "AppData" / "Roaming"))) / "Microsoft",
        ]
    else:
        roots += [Path(p) for p in ("/etc", "/bin", "/sbin", "/usr", "/boot", "/sys", "/proc")]
    return roots


def _spawn(argv: list[str]) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(  # noqa: S603 - exact allow-listed command, no shell
        argv,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def inside(child: Path, root: Path) -> bool:
    c, r = _norm(child), _norm(root)
    return c == r or c.startswith(r.rstrip(os.sep) + os.sep)


@dataclass
class Policy:
    enabled: bool = False
    paused: bool = False
    apps: list[dict[str, str]] = field(default_factory=list)
    folders: list[dict[str, Any]] = field(default_factory=list)
    browser: bool = False
    screen: bool = False
    claude_code: bool = False

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Policy:
        return cls(
            enabled=bool(raw.get("enabled")),
            paused=bool(raw.get("paused")),
            apps=[
                {"name": str(a.get("name", "")), "command": str(a.get("command", ""))}
                for a in raw.get("apps") or []
                if isinstance(a, dict)
            ],
            folders=[
                {"path": str(f.get("path", "")), "write": bool(f.get("write"))}
                for f in raw.get("folders") or []
                if isinstance(f, dict)
            ],
            browser=bool(raw.get("browser")),
            screen=bool(raw.get("screen")),
            claude_code=bool(raw.get("claude_code")),
        )


class Operator:
    def __init__(self, control: bool) -> None:
        self.control = control  # switched on locally by the owner
        self.policy = Policy()  # nothing allowed until NEXUS sends the policy
        self.running: dict[str, asyncio.Task[Any]] = {}
        self.history: list[dict[str, Any]] = []  # recent actions, newest last
        self.extra: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {}
        self.on_stop: list[Callable[[], Awaitable[None]]] = []

    # --- policy ------------------------------------------------------------------

    def set_policy(self, raw: dict[str, Any]) -> None:
        self.policy = Policy.parse(raw)

    def check(self, what: str | None = None) -> None:
        if not self.control:
            raise Refused(
                "Computer control is switched off on this PC. Run: nexus-agent control on"
            )
        p = self.policy
        if not p.enabled:
            raise Refused("Computer control is off in NEXUS settings.")
        if p.paused:
            raise Refused("Computer control is paused.")
        if what and not getattr(p, what):
            raise Refused(f"{what.replace('_', ' ').capitalize()} is off in NEXUS settings.")

    def folder(self, raw: str, *, write: bool, must_exist: bool = True) -> Path:
        """Resolve a path on this PC and check it stays in an allowed folder."""
        target = Path(raw).expanduser()
        if not target.is_absolute():
            raise Refused("Use a full path.")
        resolved = target.resolve(strict=False)
        if must_exist and not resolved.exists():
            raise Refused(f"{raw} doesn't exist.")
        for blocked in _blocked_roots():
            with contextlib.suppress(OSError):
                if inside(resolved, blocked.resolve()):
                    raise Refused("NEXUS never touches system or credential folders.")
        for f in self.policy.folders:
            root = Path(f["path"]).expanduser().resolve(strict=False)
            if inside(resolved, root):
                if write and not f["write"]:
                    raise Refused(f"{f['path']} is read-only for NEXUS.")
                return resolved
        if _norm(resolved) != _norm(Path(os.path.normpath(target.absolute()))):
            raise Refused("That path is a link that leads outside the allowed folders.")
        raise Refused("That path isn't in an allowed folder.")

    # --- calls -------------------------------------------------------------------

    async def handle_call(self, msg: dict[str, Any]) -> dict[str, Any]:
        call_id, tool = str(msg.get("id", "")), str(msg.get("tool", ""))
        args = msg.get("input") if isinstance(msg.get("input"), dict) else {}
        started = datetime.now(UTC)
        task = asyncio.create_task(self._dispatch(tool, args or {}))
        self.running[call_id] = task
        try:
            output = await task
            reply = {"type": "result", "id": call_id, "ok": True, "output": output}
        except Refused as exc:
            reply = {"type": "result", "id": call_id, "ok": False, "error": str(exc)}
        except asyncio.CancelledError:
            reply = {"type": "result", "id": call_id, "ok": False, "error": "Stopped."}
        except Exception as exc:
            log.exception("action %s failed", tool)
            reply = {
                "type": "result",
                "id": call_id,
                "ok": False,
                "error": f"{tool} failed on the PC ({type(exc).__name__}).",
            }
        finally:
            self.running.pop(call_id, None)
        self.history = [
            *self.history[-49:],
            {
                "tool": tool,
                "ok": reply["ok"],
                "at": started.isoformat(),
                "error": reply.get("error"),
            },
        ]
        log.info("action %s %s", tool, "done" if reply["ok"] else f"refused: {reply.get('error')}")
        return reply

    async def stop(self) -> None:
        """Kill switch: cancel everything now."""
        self.policy.paused = True
        for task in list(self.running.values()):
            task.cancel()
        for hook in self.on_stop:
            with contextlib.suppress(Exception):
                await hook()
        log.warning("Stopped by NEXUS: computer control paused.")

    async def _dispatch(self, tool: str, a: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
            "open_app": self.open_app,
            "open_url": self.open_url,
            "files_list": self.files_list,
            "files_read": self.files_read,
            "files_write": self.files_write,
            "files_move": self.files_move,
            **self.extra,
        }
        fn = handlers.get(tool)
        if fn is None:
            raise Refused(f"This PC can't do {tool} (not installed or not supported).")
        return await fn(a)

    # --- apps and links ------------------------------------------------------------

    async def open_app(self, a: dict[str, Any]) -> dict[str, Any]:
        self.check()
        name, command = str(a.get("name", "")), str(a.get("command", ""))
        allowed = next(
            (x for x in self.policy.apps if x["name"] == name and x["command"] == command), None
        )
        if allowed is None:
            raise Refused(f"'{name}' isn't an allowed app on this PC.")
        argv = shlex.split(command, posix=sys.platform != "win32")
        if not argv:
            raise Refused("That app has no command.")
        try:
            await asyncio.to_thread(_spawn, argv)
        except OSError as exc:
            raise Refused(f"Couldn't start {name}: {exc.strerror or exc}.") from exc
        return {"started": name}

    async def open_url(self, a: dict[str, Any]) -> dict[str, Any]:
        self.check()
        url = str(a.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise Refused("Only web addresses can be opened.")
        await asyncio.to_thread(webbrowser.open, url)
        return {"opened": url}

    # --- files ---------------------------------------------------------------------

    async def files_list(self, a: dict[str, Any]) -> dict[str, Any]:
        self.check()
        path = self.folder(str(a.get("path", "")), write=False)
        if not path.is_dir():
            raise Refused("That isn't a folder.")
        entries: list[dict[str, Any]] = []
        for child in sorted(path.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            if len(entries) >= MAX_LIST:
                break
            with contextlib.suppress(OSError):
                st = child.stat()
                entries.append(
                    {
                        "name": child.name,
                        "dir": child.is_dir(),
                        "size": st.st_size if child.is_file() else None,
                        "modified": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
                    }
                )
        return {"path": str(path), "entries": entries, "more": len(entries) >= MAX_LIST}

    async def files_read(self, a: dict[str, Any]) -> dict[str, Any]:
        self.check()
        path = self.folder(str(a.get("path", "")), write=False)
        if not path.is_file():
            raise Refused("That isn't a file.")
        if path.suffix.lower() not in TEXT_TYPES:
            raise Refused(
                f"NEXUS reads text files on the PC; {path.suffix or 'this type'} isn't one."
            )
        limit = min(int(a.get("max_chars", 20000)), 50000)
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read(limit + 1)
        return {"path": str(path), "text": text[:limit], "truncated": len(text) > limit}

    async def files_write(self, a: dict[str, Any]) -> dict[str, Any]:
        self.check()
        content = str(a.get("content", ""))
        if len(content) > MAX_WRITE:
            raise Refused("That's too much text for one file.")
        path = self.folder(str(a.get("path", "")), write=True, must_exist=False)
        if path.exists() and not a.get("overwrite"):
            raise Refused(f"{path.name} already exists. Ask to overwrite it.")
        if path.exists() and not path.is_file():
            raise Refused("That path is a folder.")
        self.folder(str(path.parent), write=True, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.nexus-tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
        return {"written": str(path), "chars": len(content)}

    async def files_move(self, a: dict[str, Any]) -> dict[str, Any]:
        self.check()
        src = self.folder(str(a.get("source", "")), write=True)
        dest = self.folder(str(a.get("destination", "")), write=True, must_exist=False)
        if dest.exists():
            raise Refused(f"{dest.name} already exists; NEXUS won't replace it.")
        self.folder(str(dest.parent), write=True)
        shutil.move(src, dest)
        return {"moved": str(src), "to": str(dest)}
