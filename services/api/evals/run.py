"""Run the agent evals against your local model.

    cd services/api
    NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_eval \\
        uv run python -m evals.run [--only add-task] [--record]

Needs Ollama or LM Studio running with your chat model. Uses a separate database whose
name ends in _eval, which it clears between scenarios; it refuses any other database so
your real data is never touched. --record writes the model's answers back into
scenarios.json as the recordings CI replays."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from typing import Any

os.environ.setdefault("NEXUS_ENV", "test")


async def main(only: list[str], record: bool) -> int:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    import app.models  # noqa: F401  (registers every table on Base.metadata)
    from app.ai.gateway import get_gateway
    from app.core.config import get_settings
    from app.db.base import Base
    from app.db.session import dispose_engine, get_sessionmaker
    from app.main import create_app
    from evals import harness

    url = get_settings().database_url
    if not url.rsplit("/", 1)[-1].endswith("_eval"):
        print("Refusing: point NEXUS_DATABASE_URL at a database whose name ends in _eval.")
        return 2
    gateway = get_gateway()
    recorder = Recorder(gateway.providers["local"]) if record else None
    if recorder is not None:
        gateway.providers["local"] = recorder
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    scenarios = [s for s in harness.load() if not only or s["id"] in only]
    results = []
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://eval") as c:
        for sc in scenarios:
            async with get_sessionmaker()() as db:
                await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
                await db.commit()
            owner = {
                "email": "eval@example.com",
                "password": "eval horse battery",
                "display_name": "Tarun",
            }
            await c.post("/api/v1/auth/register", json=owner)
            tok = (
                await c.post(
                    "/api/v1/auth/login", json={k: owner[k] for k in ("email", "password")}
                )
            ).json()
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            if recorder is not None:
                recorder.start()
            t0 = time.perf_counter()
            res = await harness.run_scenario(c, h, sc)
            ms = int((time.perf_counter() - t0) * 1000)
            results.append(res)
            mark = "PASS" if res.passed else "FAIL"
            print(f"{mark}  {sc['id']:<28} {ms:>6} ms  calls={res.calls}")
            for p in res.problems:
                print(f"      - {p}")
            if recorder is not None and res.passed:
                sc["recorded"] = recorder.responses
    await dispose_engine()
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} scenarios passed")
    if record:
        all_sc = {s["id"]: s for s in harness.load()}
        all_sc.update({s["id"]: s for s in scenarios})
        harness.SCENARIOS.write_text(
            json.dumps(list(all_sc.values()), indent=2, ensure_ascii=False) + "\n"
        )
        print("Recordings saved for the scenarios that passed.")
    return 0 if passed == len(results) else 1


class Recorder:
    """Wraps the local provider and keeps each answer in scenarios.json's format."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.name = inner, inner.name
        self.responses: list[Any] = []

    def start(self) -> None:
        self.responses = []

    def available(self) -> bool:
        return bool(self.inner.available())

    async def complete(self, req: Any, on_text: Any = None) -> Any:
        resp = await self.inner.complete(req, on_text)
        if resp.tool_calls:
            self.responses.append([{"name": c.name, "input": c.input} for c in resp.tool_calls])
        else:
            self.responses.append(resp.text)
        return resp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", nargs="*", default=[], help="scenario ids")
    ap.add_argument("--record", action="store_true", help="save passing answers as recordings")
    args = ap.parse_args()
    subprocess.run(["alembic", "upgrade", "head"], check=True, capture_output=True)  # noqa: S607
    sys.exit(asyncio.run(main(args.only, args.record)))
