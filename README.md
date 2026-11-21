# NEXUS AI

A personal AI operating system: one assistant, one memory and one command centre for work and personal life,
used by chat and voice on the web, a Windows desktop app and a phone PWA.

- Design: [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md)
- Engineering rules for coding agents: [`CLAUDE.md`](CLAUDE.md)
- Current phase and its gate: [`docs/phases/`](docs/phases/)

## Layout

| Path | What it is |
| --- | --- |
| `services/api` | FastAPI backend, Alembic migrations, Arq worker (`app/worker.py`: mail and calendar sync, briefings, document reading) |
| `apps/web` | Next.js web app (also the UI inside the Tauri desktop app and the PWA) |
| `docs` | Blueprint, phase plans and phase prompts |

## Run it on Windows (quick start)

NEXUS is local-first: the AI runs on your own PC, so there's no cost and nothing leaves your machine.

1. **Install the tools.** [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [Git](https://git-scm.com/download/win).
2. **Install a local model server.** Pick one:
   - [Ollama](https://ollama.com/download). Then in PowerShell run `ollama pull qwen3:14b` and `ollama pull bge-m3`. Ollama uses your AMD GPU through Vulkan/ROCm.
   - [LM Studio](https://lmstudio.ai). Download a Qwen3 14B (Q4_K_M) model, open the Developer tab and start the server on port 1234. In `.env`, set `NEXUS_LOCAL_BASE_URL_DOCKER=http://host.docker.internal:1234/v1`, set `NEXUS_LOCAL_MODEL` to the model id that LM Studio shows, and set `NEXUS_EMBEDDING_PROVIDER=none` (or keep Ollama running only for `bge-m3`).
3. **Get the code and create your settings.**
   ```powershell
   git clone https://github.com/TARUN-0514/infiops.git
   cd infiops
   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
   ```
4. **Start NEXUS.** Run `docker compose up -d --build`. The first build takes a few minutes.
5. **Open it.** Go to http://localhost:3000 and create your owner account. On your phone, use http://YOUR-PC-IP:3000 while on the same Wi-Fi.
6. **Check the AI.** Settings › AI models should say *Connected*. If it doesn't, make sure Ollama or LM Studio is running and the model has been downloaded.

To stop it, run `docker compose down`. Your data stays in Docker volumes.

**Optional cloud for hard tasks.** Set `NEXUS_CLOUD_ENABLED=true` and `NEXUS_ANTHROPIC_API_KEY=…` in `.env`, then run `docker compose up -d` again. Chat then shows a **Use cloud** switch that you turn on for one message at a time. `NEXUS_CLOUD_DAILY_TOKEN_BUDGET` caps how much it can use per day.

## Connect Google (email and calendar)

NEXUS reads your mail, writes drafts and manages calendar events. It never sends an email until you approve that exact email.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project, then enable the **Gmail API** and the **Google Calendar API** (APIs & Services › Library).
2. Open **Google Auth Platform** (OAuth consent screen). Choose *External*, fill in the app name and your email, and add yourself under **Test users**. Add these scopes: `gmail.readonly`, `gmail.compose`, `calendar.events`.
3. Under **Clients**, create an OAuth client of type *Web application* with this authorised redirect URI:
   `http://localhost:3000/api/v1/integrations/google/callback`
   (If you open NEXUS at another address, use that address and set `NEXUS_PUBLIC_WEB_URL` to match.)
4. Put the client id and secret in `.env` as `NEXUS_GOOGLE_CLIENT_ID` and `NEXUS_GOOGLE_CLIENT_SECRET`, then run `docker compose up -d` again.
5. In NEXUS, open **Settings › Integrations** and press **Connect Google**. It shows *Connected* only after a real Gmail and Calendar call works.

While the app is in *Testing* mode, Google asks you to sign in again every 7 days. That's expected for a personal app.

**Reading images in documents (optional).** Run `ollama pull qwen2.5vl:7b` and set `NEXUS_LOCAL_MODEL_VISION=qwen2.5vl:7b`.

**Notifications.** Turn them on in **Settings › Integrations**. Browsers allow push only on `localhost` or `https://`, so on your phone it works once NEXUS is served over HTTPS.

## Run locally (development)

Requirements: Docker, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm.

```bash
./scripts/setup.sh            # creates .env with fresh secrets
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
cd services/api && uv run pytest          # needs Postgres with pgvector (nexus_test database) and Redis
cd apps/web && pnpm test
```

Model calls in tests use a scripted provider, so tests never need a model server.

**Phase 1 gate (task parsing).** With your model server running, this checks 20 everyday sentences:

```bash
cd services/api && uv run python scripts/eval_task_parsing.py          # local model
cd services/api && uv run python scripts/eval_task_parsing.py --cloud  # cloud model, if enabled
```
