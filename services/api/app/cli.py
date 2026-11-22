"""Command-line checks.

    python -m app.cli restore-check --database nexus_restore_check [--backup latest]

Checks a database restored from a backup (see infra/backup/restore.sh): its schema
revision matches the backup and this code, every table has exactly the rows the backup
counted, and encrypted finance, health, journal and account-token values decrypt with this
machine's NEXUS_ENCRYPTION_KEY. Prints a JSON report and exits 1 if anything is wrong."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import make_url, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import app.models
from app.core.config import get_settings
from app.services.integrations import encryptor

SAMPLE = 25
ENCRYPTED = (
    app.models.FinancialAccount,
    app.models.Transaction,
    app.models.HealthLog,
    app.models.WorkoutSession,
    app.models.JournalEntry,
)


def code_head() -> str | None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def find_backup(name: str) -> Path:
    root = Path(get_settings().backup_dir)
    if name == "latest":
        found = sorted(p.parent for p in root.glob("2*/manifest.json"))
        if not found:
            raise SystemExit(f"No backups in {root}.")
        return found[-1]
    path = root / name
    if not (path / "manifest.json").is_file():
        raise SystemExit(f"No backup called {name} in {root}.")
    return path


async def _counts(engine: AsyncEngine, tables: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    async with engine.connect() as conn:
        present = set(
            (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                    )
                )
            ).scalars()
        )
        for t in tables:
            if t in present:
                # table names come from information_schema, quoted
                n = await conn.scalar(text(f'SELECT count(*) FROM public."{t}"'))  # noqa: S608
                out[t] = int(n or 0)
    return out


async def restore_check(database: str, backup: str = "latest") -> dict[str, Any]:
    folder = find_backup(backup)
    manifest: dict[str, Any] = json.loads((folder / "manifest.json").read_text())
    url = make_url(get_settings().database_url).set(database=database)
    engine = create_async_engine(url)
    problems: list[str] = []
    report: dict[str, Any] = {"backup": folder.name, "database": database}
    try:
        async with engine.connect() as conn:
            revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        head = code_head()
        report["revision"] = {"restored": revision, "backup": manifest.get("alembic_revision")}
        if revision != manifest.get("alembic_revision"):
            problems.append(f"Schema revision {revision} doesn't match the backup's.")
        if revision != head:
            report["upgrade_needed"] = f"Run alembic upgrade head ({revision} → {head})."

        expected: dict[str, int] = manifest.get("counts", {})
        actual = await _counts(engine, list(expected))
        mismatched = {
            t: {"backup": n, "restored": actual.get(t)}
            for t, n in expected.items()
            if actual.get(t) != n
        }
        report["tables"] = len(expected)
        report["rows"] = sum(actual.values())
        if mismatched:
            report["mismatched"] = mismatched
            problems.append(f"{len(mismatched)} tables don't have the rows the backup counted.")

        decrypted = 0
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as db:
            for model in ENCRYPTED:
                try:
                    decrypted += len(list(await db.scalars(select(model).limit(SAMPLE))))
                except Exception:
                    problems.append(
                        f"{model.__tablename__} won't decrypt: this machine's "
                        "NEXUS_ENCRYPTION_KEY isn't the one the backup was made with."
                    )
                    break
            enc = encryptor()
            for account in await db.scalars(select(app.models.ConnectedAccount).limit(SAMPLE)):
                for blob in (account.access_token_enc, account.refresh_token_enc):
                    if blob:
                        try:
                            enc.decrypt(blob, account.id.bytes)
                            decrypted += 1
                        except Exception:
                            problems.append(
                                "Account tokens won't decrypt with this machine's "
                                "NEXUS_ENCRYPTION_KEY."
                            )
                            break
        report["decrypted_samples"] = decrypted
    finally:
        await engine.dispose()
    report["ok"] = not problems
    report["problems"] = problems
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    rc = sub.add_parser("restore-check", help="check a database restored from a backup")
    rc.add_argument("--database", required=True)
    rc.add_argument("--backup", default="latest")
    args = parser.parse_args(argv)
    if args.database == make_url(get_settings().database_url).database:
        print("Point --database at the restored copy, not the live database.", file=sys.stderr)
        return 2
    report = asyncio.run(restore_check(args.database, args.backup))
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
