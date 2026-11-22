"""Write the API reference from the code, so it can't drift.

uv run python scripts/export_openapi.py          # write docs/api/openapi.json and docs/API.md
uv run python scripts/export_openapi.py --check  # exit 1 if they are out of date (CI)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("NEXUS_ENV", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs" / "api" / "openapi.json"
GUIDE = ROOT / "docs" / "API.md"
METHODS = ("get", "post", "put", "patch", "delete")

INTRO = """# NEXUS API

The web app, the Windows app, the phone and the local agent all use this API. The full
machine-readable contract is [`api/openapi.json`](api/openapi.json); while developing, the
interactive version is at http://localhost:8000/api/v1/docs (turned off in production).
This page and `openapi.json` are generated from the code by
`services/api/scripts/export_openapi.py`, and CI fails if they are out of date.

## Signing in

1. `POST /api/v1/auth/login` with `{"email", "password"}` (and `"totp_code"` when
   two-factor is on) returns `{"access_token", "expires_in"}` and sets two cookies: an
   httpOnly refresh token and `nexus_csrf`.
2. Send `Authorization: Bearer <access_token>` on every call. Access tokens last 15 minutes.
3. `POST /api/v1/auth/refresh` with the header `X-CSRF-Token: <nexus_csrf cookie>` returns a
   new access token and rotates the refresh token. Reusing an old refresh token signs out
   that session.

The first account registered becomes the owner; registration then closes. Sign-in is
rate limited per address.

## Errors

Every error has the same shape and a status code that means what it says:

```json
{"error": {"code": "validation_error", "message": "Check the highlighted fields.",
           "fields": [{"field": "title", "message": "Field required"}]}}
```

`400` the request can't be done as asked (for example a draft locked while its send waits
for approval), `401` signed out or token expired, `403` not allowed, `404` not yours or not
there, `413` upload too large, `422` invalid input, `429` too many sign-in attempts.

## Actions that need approval

Tools the assistant runs are checked on the server against their risk level. A sensitive
or irreversible action (sending an email, deleting a task or an event, writing files)
creates an approval request instead of running: list them with `GET /api/v1/approvals`
and decide with `POST /api/v1/approvals/{id}/decide` `{"approve": true}`. Nothing a model
says can approve one. See [SECURITY-REVIEW.md](SECURITY-REVIEW.md).

## Chat streaming

`POST /api/v1/chat/conversations/{id}/messages` streams newline-delimited JSON events
(`run.started`, `memory.used`, `text.delta`, `tool.started`, `tool.finished`,
`approval.required`, `message.completed`, `run.finished`).
The run continues and is saved even if the client disconnects.

## Endpoints
"""


def build() -> tuple[str, str]:
    spec: dict[str, Any] = create_app().openapi()
    spec_text = json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    groups: dict[str, list[tuple[str, str, str, bool]]] = {}
    for path, ops in sorted(spec["paths"].items()):
        for method in METHODS:
            op = ops.get(method)
            if op is None:
                continue
            tag = (op.get("tags") or ["other"])[0]
            summary = (op.get("description") or op.get("summary") or "").strip().split("\n")[0]
            groups.setdefault(tag, []).append(
                (method.upper(), path, summary.replace("|", "\\|"), bool(op.get("security")))
            )
    lines = [INTRO]
    count = sum(len(v) for v in groups.values())
    lines.append(f"{count} endpoints in {len(groups)} groups. 🔒 means a signed-in owner only.\n")
    for tag in sorted(groups):
        lines.append(f"\n### {tag.capitalize()}\n")
        lines.append("| Method | Path | What it does |")
        lines.append("| --- | --- | --- |")
        for method, path, summary, secured in groups[tag]:
            lock = " 🔒" if secured else ""
            lines.append(f"| {method} | `{path}`{lock} | {summary} |")
    return spec_text, "\n".join(lines) + "\n"


def main() -> int:
    spec_text, guide = build()
    if "--check" in sys.argv:
        stale = [
            str(p.relative_to(ROOT))
            for p, text in ((SPEC, spec_text), (GUIDE, guide))
            if not p.exists() or p.read_text() != text
        ]
        if stale:
            print("Out of date: " + ", ".join(stale))
            print("Run: cd services/api && uv run python scripts/export_openapi.py")
            return 1
        return 0
    SPEC.parent.mkdir(parents=True, exist_ok=True)
    SPEC.write_text(spec_text)
    GUIDE.write_text(guide)
    print(f"wrote {SPEC.relative_to(ROOT)} and {GUIDE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
