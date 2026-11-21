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
| `apps/desktop` | Windows app (Tauri 2): window, tray, Ctrl+Shift+Space push-to-talk, notifications |
| `services/voice` | Local voice server: Whisper speech recognition and Piper voice |
| `services/local-agent` | `nexus-agent` for your PC: wake word, hands-free voice, computer control, link to NEXUS |
| `infra/searxng` | Settings for the private search server used by research |
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

## Voice

Voice runs on your PC. `docker compose up -d` starts the `voice` service (Whisper for speech recognition, Piper for the voice). The first start downloads the models, about 200 MB.

- **Talk:** press the mic button or **Ctrl+Shift+Space** on any page, speak, and pause. NEXUS answers out loud. Talk over it to interrupt. Each answer shows how long it took to start speaking.
- **Check it:** Settings › Voice and devices tests both parts with a real call.
- **More accurate recognition:** set `NEXUS_VOICE_STT_MODEL=small.en` in `.env` and run `docker compose up -d voice`.
- **Use the GPU (fastest):** download a Vulkan build of [whisper.cpp](https://github.com/ggml-org/whisper.cpp) for Windows and a model such as `ggml-large-v3-turbo-q5_0.bin`, then run `whisper-server -m ggml-large-v3-turbo-q5_0.bin --port 8178`. In `.env`, set `NEXUS_STT_URL_DOCKER=http://host.docker.internal:8178/inference` and run `docker compose up -d api`.
- On a phone, the microphone works only over `https://` (a browser rule).

### Wake word and hands-free (local agent)

The local agent listens on your PC for "Hey Jarvis", and can keep listening for follow-ups. It is off until you turn it on.

```powershell
winget install astral-sh.uv          # once
cd infiops\services\local-agent
uv tool install --python 3.12 ".[audio]"
```

In NEXUS, open Settings › Voice and devices, press **Pair a PC**, and run the command it shows (`nexus-agent pair --code XXXX-XXXX`). Then run `nexus-agent run` (the Windows app starts it for you). Turn on **Wake word** or **Hands-free** for that PC in Settings. **Stop listening** there closes the microphone at once, and **Remove** ends the agent's access.

## Computer control (apps, folders, browser, screen, Claude Code)

NEXUS can work on your PC through the local agent. Everything is off until you allow it, in two places:

1. **On the PC:** `nexus-agent control on`, then restart the agent. `nexus-agent control off` blocks it again, whatever the web settings say.
2. **In NEXUS:** Settings › Computer control. Turn on Computer control, add the folders NEXUS may use (tick **Can write** only where it may create or move files) and the apps it may open (exact command, run without a shell). Turn on NEXUS's own browser, Claude Code or Screen control separately.

Reading and listing run straight away. Writing or moving a file, browser actions, Claude Code and screen control each wait for your OK. NEXUS never deletes files. System folders, credential folders (`.ssh`, `.aws`) and the agent's own folder are refused on the PC even if you allow a parent folder. **Stop everything** (Settings › Computer control, or AI Assistant › Activity) cancels whatever is running on the PC and pauses control until you resume. Every action is listed under AI Assistant › Activity.

Optional extras on the PC:

```powershell
uv tool install --python 3.12 ".[audio,browser,screen]"   # in services\local-agent
playwright install chromium                               # NEXUS's own browser profile
npm install -g @anthropic-ai/claude-code                  # for Claude Code runs
```

- **NEXUS's own browser** is Chromium with a separate profile in `%APPDATA%\NEXUS\browser-profile`. It never sees your own browser, passwords or sign-ins, and won't type into password fields.
- **Claude Code** runs in an allowed project folder, plan-only unless you allow edits for that run. It uses your own Claude Code sign-in on the PC.
- **Screen control** uses Claude's computer-use tool, so it needs cloud turned on (`NEXUS_CLOUD_ENABLED=true` and an API key) and sends screenshots to Claude. Move the mouse into a screen corner to stop it instantly.

## Research and web search

Research uses a private SearXNG search server on your PC. No API key or paid service:

```bash
docker compose up -d search        # http://localhost:8888
```

Set `SEARXNG_SECRET` in `.env` to any long random string. Ask in chat, or use AI Assistant › Research. NEXUS searches, reads up to five pages, and labels each finding **verified** (a page it read says so, with the source number), **assumption** or **opinion**. A claim the model marks verified without a page that backs it is downgraded on the server. NEXUS won't read pages on your home network or `localhost`.

## GitHub (read-only)

1. On GitHub, Settings › Developer settings › Fine-grained tokens, make a token for only the repositories you want, with **read-only** access to Contents, Pull requests and Issues.
2. In `.env`: `NEXUS_GITHUB_TOKEN=github_pat_...` and `NEXUS_GITHUB_REPOS=["TARUN-0514/Infiops"]`.
3. Settings › Integrations › GitHub › **Test**. It shows connected only when GitHub answers.

NEXUS can then list and summarise pull requests and issues and review diffs. It can't comment, push or merge.

## Finance

Finance › Transactions takes quick entries like `450 swiggy dinner` or `salary 85000`, read on the server with no model. You can also say it in chat or by voice ("spent 450 on Swiggy"). To import, download a CSV statement from your bank or card and drop it on Finance › Import. NEXUS finds the date, description and amount columns (including separate debit and credit columns or a Dr/Cr marker), shows a preview, and skips rows it already has, so importing the same file twice is safe.

- Amounts, descriptions and notes are encrypted in the database with `NEXUS_ENCRYPTION_KEY`. Keep a copy of that key: without it the data can't be read.
- Finance and health tools only run on the local model. When you turn on Use cloud, they're hidden, money and health memories are left out, and a chat that already has money or health details stays on your PC.
- EMIs and bills send a reminder before they're due (hourly worker job, after 8 AM your time). Mark paid records the spending. NEXUS never pays anything.

## Fitness

Fitness logs workouts with sets (reps, weight, time or distance), body weight and measurements, calories, protein, water, sleep and habits, all encrypted the same way. This week compares with last week, and Month tracked shows which days have spending and workouts. It's tracking, not medical advice.

## Windows app

The Windows app shows NEXUS in its own window, adds a tray icon, makes Ctrl+Shift+Space work from any app, shows Windows notifications, and starts the local agent.

To build it you need [Rust](https://rustup.rs) and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) (Microsoft C++ Build Tools and WebView2, already on Windows 11):

```powershell
cd apps/desktop
pnpm install
pnpm build        # installer in src-tauri/target/release/bundle/
```

It opens http://localhost:3000. To use another address, or to stop it starting the agent, create `%APPDATA%\NEXUS\desktop.json`:

```json
{ "url": "http://localhost:3000", "start_agent": true, "agent_command": ["nexus-agent", "run"] }
```

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
cd services/voice && uv run pytest
cd services/local-agent && uv run pytest
cd apps/desktop/src-tauri && cargo clippy -- -D warnings
```

Model calls in tests use a scripted provider, so tests never need a model server.

**Phase 1 gate (task parsing).** With your model server running, this checks 20 everyday sentences:

```bash
cd services/api && uv run python scripts/eval_task_parsing.py          # local model
cd services/api && uv run python scripts/eval_task_parsing.py --cloud  # cloud model, if enabled
```
