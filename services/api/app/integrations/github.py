"""GitHub, read-only: pull requests, diffs and issues in the repositories the owner allowed."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

API = "https://api.github.com"
_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = transport


class GitHubError(LookupError):
    pass


def ready() -> bool:
    return bool(get_settings().github_token.get_secret_value())


def allowed_repos() -> list[str]:
    return [r.strip() for r in get_settings().github_repos if r.strip()]


def check_repo(repo: str) -> str:
    repo = repo.strip().removeprefix("https://github.com/").strip("/")
    allowed = allowed_repos()
    for name in allowed:
        if name.lower() == repo.lower():
            return name
    listed = ", ".join(allowed) or "none (set NEXUS_GITHUB_REPOS)"
    raise GitHubError(f"NEXUS isn't allowed to read {repo}. Allowed: {listed}.")


async def _get(path: str, params: dict[str, Any] | None = None, accept: str | None = None) -> Any:
    token = get_settings().github_token.get_secret_value()
    if not token:
        raise GitHubError("GitHub isn't connected. Add NEXUS_GITHUB_TOKEN (see README).")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept or "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "NEXUS",
    }
    try:
        async with httpx.AsyncClient(transport=_transport, timeout=20) as http:
            r = await http.get(API + path, params=params, headers=headers)
    except httpx.TransportError as exc:
        raise GitHubError("Can't reach GitHub.") from exc
    if r.status_code == 401:
        raise GitHubError("GitHub rejected the token. Make a new one (see README).")
    if r.status_code in (403, 404):
        raise GitHubError("GitHub says the token can't see that. Check its repository access.")
    if r.status_code >= 400:
        raise GitHubError(f"GitHub returned {r.status_code}.")
    return r.text if accept and "diff" in accept else r.json()


async def test() -> dict[str, Any]:
    """Real call: who the token belongs to, and which allowed repos it can read."""
    me = await _get("/user")
    repos: list[dict[str, Any]] = []
    for repo in allowed_repos():
        try:
            data = await _get(f"/repos/{repo}")
            repos.append({"repo": repo, "ok": True, "private": data.get("private", False)})
        except GitHubError as exc:
            repos.append({"repo": repo, "ok": False, "error": str(exc)})
    return {"login": me.get("login"), "repos": repos}


def _pr(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": p["number"],
        "title": p.get("title"),
        "author": (p.get("user") or {}).get("login"),
        "state": p.get("state"),
        "draft": p.get("draft", False),
        "url": p.get("html_url"),
        "updated_at": p.get("updated_at"),
    }


async def pulls(repo: str, state: str = "open") -> list[dict[str, Any]]:
    repo = check_repo(repo)
    data = await _get(f"/repos/{repo}/pulls", {"state": state, "per_page": 20})
    return [_pr(p) for p in data]


async def pull(repo: str, number: int, max_patch: int = 12000) -> dict[str, Any]:
    repo = check_repo(repo)
    p = await _get(f"/repos/{repo}/pulls/{number}")
    files = await _get(f"/repos/{repo}/pulls/{number}/files", {"per_page": 50})
    patch: list[str] = []
    used = 0
    for f in files:
        counts = f"+{f.get('additions')} -{f.get('deletions')}"
        chunk = f"--- {f['filename']} ({f.get('status')}, {counts})\n"
        chunk += (f.get("patch") or "")[:3000]
        if used + len(chunk) > max_patch:
            patch.append(f"... {len(files) - len(patch)} more files not shown")
            break
        patch.append(chunk)
        used += len(chunk)
    return {
        **_pr(p),
        "body": (p.get("body") or "")[:4000],
        "base": p.get("base", {}).get("ref"),
        "head": p.get("head", {}).get("ref"),
        "additions": p.get("additions"),
        "deletions": p.get("deletions"),
        "changed_files": p.get("changed_files"),
        "mergeable_state": p.get("mergeable_state"),
        "diff": "\n".join(patch),
    }


async def issues(repo: str, state: str = "open") -> list[dict[str, Any]]:
    repo = check_repo(repo)
    data = await _get(f"/repos/{repo}/issues", {"state": state, "per_page": 20})
    return [
        {
            "number": i["number"],
            "title": i.get("title"),
            "author": (i.get("user") or {}).get("login"),
            "labels": [lb.get("name") for lb in i.get("labels", [])],
            "comments": i.get("comments"),
            "url": i.get("html_url"),
            "updated_at": i.get("updated_at"),
        }
        for i in data
        if "pull_request" not in i
    ]


async def issue(repo: str, number: int) -> dict[str, Any]:
    repo = check_repo(repo)
    i = await _get(f"/repos/{repo}/issues/{number}")
    comments = await _get(f"/repos/{repo}/issues/{number}/comments", {"per_page": 20})
    return {
        "number": i["number"],
        "title": i.get("title"),
        "state": i.get("state"),
        "author": (i.get("user") or {}).get("login"),
        "body": (i.get("body") or "")[:4000],
        "url": i.get("html_url"),
        "comments": [
            {"author": (c.get("user") or {}).get("login"), "body": (c.get("body") or "")[:1500]}
            for c in comments
        ],
    }
