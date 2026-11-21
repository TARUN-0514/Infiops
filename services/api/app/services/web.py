"""Web search (self-hosted SearXNG) and safe page fetching for the Research agent.

Fetched pages are untrusted: callers wrap them as data. Fetching refuses private network
addresses so a page can't make NEXUS reach into the owner's LAN."""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai import parsers
from app.core.config import get_settings
from app.services.email import html_to_text

_transport: httpx.AsyncBaseTransport | None = None
_resolver: Any = None  # tests replace DNS
USER_AGENT = "NEXUS-Research/0.1 (personal assistant)"


def set_transport(transport: httpx.AsyncBaseTransport | None, resolver: Any = None) -> None:
    global _transport, _resolver
    _transport, _resolver = transport, resolver


def _http(timeout: float = 20) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_transport,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    )


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    engine: str


async def search(query: str, limit: int = 8) -> list[SearchHit]:
    base = get_settings().searxng_url.rstrip("/")
    if not base:
        raise LookupError("Web search isn't set up. Set NEXUS_SEARXNG_URL (see README).")
    try:
        async with _http() as http:
            r = await http.get(
                f"{base}/search", params={"q": query, "format": "json", "safesearch": 1}
            )
    except httpx.TransportError as exc:
        raise LookupError(
            f"Can't reach the search server at {base}. Start it with `docker compose up -d search`."
        ) from exc
    if r.status_code == 403:
        raise LookupError("The search server refuses JSON. Enable the json format in SearXNG.")
    if r.status_code >= 400:
        raise LookupError(f"The search server returned {r.status_code}.")
    out: list[SearchHit] = []
    for item in r.json().get("results", []):
        url = str(item.get("url", ""))
        if not url.startswith(("http://", "https://")) or any(h.url == url for h in out):
            continue
        out.append(
            SearchHit(
                title=str(item.get("title", ""))[:200],
                url=url,
                snippet=re.sub(r"\s+", " ", str(item.get("content", "")))[:400],
                engine=str(item.get("engine", "")),
            )
        )
        if len(out) >= limit:
            break
    return out


async def _public(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        addrs = [ip]
    except ValueError:
        if _resolver is not None:
            addrs = [ipaddress.ip_address(a) for a in _resolver(host)]
        else:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
            addrs = [ipaddress.ip_address(i[4][0]) for i in infos]
    return bool(addrs) and all(a.is_global for a in addrs)


@dataclass
class Page:
    url: str
    title: str
    text: str
    truncated: bool


async def fetch(url: str, max_chars: int = 20000) -> Page:
    limit = get_settings().web_fetch_max_kb * 1024
    current = url
    async with _http() as http:
        for _ in range(5):  # follow redirects by hand so each hop is checked
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("Only http and https pages can be read.")
            if not await _public(parsed.hostname):
                raise ValueError("That address is on a private network, so NEXUS won't read it.")
            try:
                async with http.stream("GET", current) as r:
                    if r.is_redirect and "location" in r.headers:
                        current = str(r.url.join(r.headers["location"]))
                        continue
                    if r.status_code >= 400:
                        raise ValueError(f"The page returned {r.status_code}.")
                    body = b""
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) > limit:
                            break
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
            except httpx.TransportError as exc:
                raise ValueError(f"Couldn't load the page ({type(exc).__name__}).") from exc
            return _page(current, body, ctype, max_chars)
    raise ValueError("Too many redirects.")


def _page(url: str, body: bytes, ctype: str, max_chars: int) -> Page:
    if ctype == "application/pdf" or body[:5] == b"%PDF-":
        sections = parsers.parse(body, "application/pdf")
        text = "\n\n".join(s.text for s in sections)
        title = url.rsplit("/", 1)[-1]
    elif ctype in ("text/html", "application/xhtml+xml", ""):
        raw = body.decode("utf-8", "replace")
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
        title = html.unescape(m.group(1)).strip()[:200] if m else url
        raw = re.sub(r"(?is)<(nav|footer|header|aside|form|noscript|svg)\b.*?</\1>", " ", raw)
        text = html_to_text(raw)
    elif ctype.startswith("text/") or ctype in ("application/json", "application/xml"):
        text, title = body.decode("utf-8", "replace"), url
    else:
        raise ValueError(f"NEXUS can't read {ctype or 'this kind of'} files from the web.")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return Page(url, title or url, text[:max_chars], len(text) > max_chars)


def wrap_page(page: Page) -> str:
    return (
        f'<web_page url="{html.escape(page.url)}" title="{html.escape(page.title)}">\n'
        f"{page.text}\n</web_page>"
    )
