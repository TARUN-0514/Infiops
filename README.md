# NEXUS AI

A personal AI operating system: one assistant, one memory and one command centre for work and personal life,
used by chat and voice on the web, a Windows desktop app and a phone PWA.

- Design: [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md)
- Engineering rules for coding agents: [`CLAUDE.md`](CLAUDE.md)
- Current phase and its gate: [`docs/phases/`](docs/phases/)

## Layout

| Path | What it is |
| --- | --- |
| `services/api` | FastAPI backend, Alembic migrations, Arq worker (`app/worker.py`) |
| `apps/web` | Next.js web app (also the UI inside the Tauri desktop app and the PWA) |
| `docs` | Blueprint, phase plans and phase prompts |

## Run locally

Requirements: Docker, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm.

```bash
cp .env.example .env          # then fill NEXUS_JWT_SECRET and NEXUS_ENCRYPTION_KEY
docker compose up -d postgres redis minio

cd services/api
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload       # http://localhost:8000/api/v1/docs
uv run arq app.worker.WorkerSettings       # in another terminal

cd ../../apps/web
pnpm install
pnpm dev                                   # http://localhost:3000
```

Or run everything in containers: `docker compose up --build`.

The first account you register becomes the owner, and registration then closes.

## Tests

```bash
cd services/api && uv run pytest          # needs Postgres (nexus_test database) and Redis
cd apps/web && pnpm test
```
