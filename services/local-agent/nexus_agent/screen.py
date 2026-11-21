"""Screen control for Claude's computer-use toolset: screenshots scaled to about 1280x800 and
mouse and keyboard actions mapped back to the real screen. Every action re-checks the policy,
so Stop takes effect before the next click."""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any

from nexus_agent.operator import Operator, Refused

TARGET = (1280, 800)
KEYS = {
    "return": "enter",
    "escape": "esc",
    "super": "win",
    "cmd": "win",
    "meta": "win",
    "control": "ctrl",
    "page_up": "pageup",
    "page_down": "pagedown",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "backspace": "backspace",
}
CLICKS = {
    "left_click": ("left", 1),
    "right_click": ("right", 1),
    "middle_click": ("middle", 1),
    "double_click": ("left", 2),
    "triple_click": ("left", 3),
}
# Shortcuts NEXUS won't press: sign out, lock, task manager, closing everything.
BLOCKED = {
    ("ctrl", "alt", "del"),
    ("ctrl", "alt", "delete"),
    ("win", "l"),
    ("ctrl", "shift", "esc"),
}


def available() -> bool:
    try:
        import pyautogui  # noqa: F401
    except Exception:  # missing, or no display
        return False
    return True


class Screen:
    def __init__(self, op: Operator, gui: Any = None) -> None:
        self.op = op
        self._gui = gui

    @property
    def gui(self) -> Any:
        if self._gui is None:
            import pyautogui

            pyautogui.FAILSAFE = True  # slam the mouse into a corner to stop
            pyautogui.PAUSE = 0.05
            self._gui = pyautogui
        return self._gui

    def scale(self) -> float:
        w, h = self.gui.size()
        return float(max(w / TARGET[0], h / TARGET[1], 1.0))

    def _xy(self, coord: Any) -> tuple[int, int]:
        if not (isinstance(coord, list | tuple) and len(coord) == 2):
            raise Refused("Give a coordinate as [x, y].")
        s = self.scale()
        w, h = self.gui.size()
        x, y = round(float(coord[0]) * s), round(float(coord[1]) * s)
        if not (0 <= x < w and 0 <= y < h):
            raise Refused("That point is off the screen.")
        return x, y

    def _keys(self, text: str) -> list[str]:
        keys = [
            KEYS.get(k.strip().lower(), k.strip().lower()) for k in text.split("+") if k.strip()
        ]
        if tuple(keys) in BLOCKED:
            raise Refused("NEXUS won't press that shortcut.")
        return keys

    def _shot(self) -> dict[str, Any]:
        img = self.gui.screenshot()
        s = self.scale()
        if s > 1:
            img = img.resize((round(img.width / s), round(img.height / s)))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return {
            "image": base64.b64encode(buf.getvalue()).decode(),
            "width": img.width,
            "height": img.height,
        }

    def _do(self, action: str, a: dict[str, Any]) -> dict[str, Any]:
        g = self.gui
        if action == "screenshot":
            return self._shot()
        if action in CLICKS:
            button, n = CLICKS[action]
            if "coordinate" in a:
                g.moveTo(*self._xy(a["coordinate"]))
            g.click(button=button, clicks=n, interval=0.08)
        elif action == "mouse_move":
            g.moveTo(*self._xy(a.get("coordinate")))
        elif action == "left_click_drag":
            g.moveTo(*self._xy(a.get("start_coordinate")))
            g.dragTo(*self._xy(a.get("coordinate")), duration=0.3, button="left")
        elif action == "left_mouse_down":
            g.mouseDown(button="left")
        elif action == "left_mouse_up":
            g.mouseUp(button="left")
        elif action == "cursor_position":
            x, y = g.position()
            s = self.scale()
            return {"result": f"X={round(x / s)},Y={round(y / s)}"}
        elif action == "scroll":
            if "coordinate" in a:
                g.moveTo(*self._xy(a["coordinate"]))
            amount = max(1, min(int(a.get("scroll_amount", 3)), 20))
            direction = str(a.get("scroll_direction", "down"))
            if direction in ("up", "down"):
                g.scroll(amount * 120 * (1 if direction == "up" else -1))
            else:
                g.hscroll(amount * 120 * (1 if direction == "right" else -1))
        elif action == "type":
            g.write(str(a.get("text", ""))[:2000], interval=0.01)
        elif action == "key":
            keys = self._keys(str(a.get("text", "")))
            for _ in range(max(1, min(int(a.get("repeat", 1) or 1), 20))):
                g.hotkey(*keys)
        elif action == "hold_key":
            keys = self._keys(str(a.get("text", "")))
            for k in keys:
                g.keyDown(k)
            try:
                time.sleep(min(float(a.get("duration", 0.5)), 5))
            finally:
                for k in reversed(keys):
                    g.keyUp(k)
        else:
            raise Refused(f"This PC doesn't support the {action} action.")
        return {"result": "OK"}

    async def act(self, a: dict[str, Any]) -> dict[str, Any]:
        self.op.check("screen")
        action = str(a.get("action", ""))
        if action == "wait":
            await asyncio.sleep(min(float(a.get("duration", 1)), 10))
            return {"result": "OK"}
        return await asyncio.to_thread(self._do, action, a)


def install(op: Operator) -> Screen:
    s = Screen(op)
    op.extra["screen"] = s.act
    return s
