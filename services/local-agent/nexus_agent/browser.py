"""NEXUS's own browser: Chromium through Playwright with a separate profile in the agent's
folder, so it never sees the owner's own browser, passwords or sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from nexus_agent.config import config_dir
from nexus_agent.operator import Operator, Refused

STEP_TIMEOUT_MS = 15_000
ALLOWED_STEPS = {"click", "fill", "press", "select", "wait_for"}


def available() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    return True


class Browser:
    def __init__(self, op: Operator) -> None:
        self.op = op
        self._pw: Any = None
        self._ctx: Any = None
        self._lock = asyncio.Lock()

    async def _context(self, headless: bool) -> Any:
        if self._ctx is not None:
            return self._ctx
        from playwright.async_api import async_playwright

        profile = config_dir() / "browser-profile"
        profile.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            accept_downloads=False,
            viewport={"width": 1280, "height": 800},
        )
        # Only web pages: no file://, chrome:// or other schemes.
        await self._ctx.route(
            "**/*",
            lambda route: (
                route.continue_()
                if route.request.url.startswith(("http://", "https://", "data:", "blob:"))
                else route.abort()
            ),
        )
        return self._ctx

    async def close(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()
        self._ctx = self._pw = None

    @staticmethod
    def _url(a: dict[str, Any]) -> str:
        url = str(a.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise Refused("Only http and https pages.")
        return url

    async def _snapshot(self, page: Any) -> dict[str, Any]:
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        return {"url": page.url, "title": await page.title(), "text": str(text)[:30000]}

    async def read(self, a: dict[str, Any]) -> dict[str, Any]:
        self.op.check("browser")
        url = self._url(a)
        async with self._lock:
            ctx = await self._context(headless=True)
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(800)
                return await self._snapshot(page)
            finally:
                await page.close()

    async def act(self, a: dict[str, Any]) -> dict[str, Any]:
        self.op.check("browser")
        url = self._url(a)
        steps = a.get("steps") or []
        if not isinstance(steps, list) or not steps or len(steps) > 20:
            raise Refused("Give between 1 and 20 steps.")
        async with self._lock:
            ctx = await self._context(headless=False)
            page = await ctx.new_page()
            done: list[str] = []
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                for step in steps:
                    self.op.check("browser")  # the kill switch is checked between steps
                    do, sel = str(step.get("do")), str(step.get("selector", ""))
                    value = str(step.get("value", ""))
                    if do not in ALLOWED_STEPS:
                        raise Refused(f"Unknown step {do}.")
                    loc = page.locator(sel).first
                    if do in ("fill", "press"):
                        kind = await loc.get_attribute("type", timeout=STEP_TIMEOUT_MS)
                        if (kind or "").lower() == "password":
                            raise Refused("NEXUS never types into password fields.")
                    if do == "click":
                        await loc.click(timeout=STEP_TIMEOUT_MS)
                    elif do == "fill":
                        await loc.fill(value, timeout=STEP_TIMEOUT_MS)
                    elif do == "press":
                        await loc.press(value or "Enter", timeout=STEP_TIMEOUT_MS)
                    elif do == "select":
                        await loc.select_option(value, timeout=STEP_TIMEOUT_MS)
                    else:
                        await loc.wait_for(timeout=STEP_TIMEOUT_MS)
                    done.append(f"{do} {sel}")
                await page.wait_for_timeout(500)
                return {**await self._snapshot(page), "steps_done": done}
            finally:
                await page.close()


def install(op: Operator) -> Browser:
    b = Browser(op)
    op.extra["browser_read"] = b.read
    op.extra["browser_act"] = b.act
    op.on_stop.append(b.close)
    return b
