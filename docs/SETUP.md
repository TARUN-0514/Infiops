# Setting up NEXUS on your Windows PC

This takes about 30 minutes, most of it downloads. When you finish, NEXUS runs on your PC.
It answers with a local AI model, and you can use it from the Windows app, a browser,
or your phone.

Everything here is free. Nothing leaves your PC unless you connect Google, or turn on the
optional cloud model for a message.

## 1. Install the tools

1. **Docker Desktop:** https://www.docker.com/products/docker-desktop/
   - During setup, keep "Use WSL 2" on.
   - Afterwards, open Settings › General and turn on **Start Docker Desktop when you sign
     in**, so NEXUS starts with your PC.
2. **Git:** https://git-scm.com/download/win
3. **A local model server.** Pick one:
   - **Ollama** (simplest): https://ollama.com/download. Then in PowerShell run:
     ```powershell
     ollama pull qwen3:14b
     ollama pull bge-m3
     ```
   - **LM Studio:** https://lmstudio.ai. Download *Qwen3 14B (Q4_K_M)*, open the Developer
     tab and start the server on port 1234. See the README's quick start for the three
     `.env` lines this needs.

   On a Radeon RX 9060 XT (16 GB), Qwen3 14B Q4 fits on the GPU with room for the context.
   Models up to about 20–24B at Q4 also fit.

## 2. Get NEXUS and create your settings

```powershell
git clone https://github.com/TARUN-0514/infiops.git
cd infiops
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This creates `.env` with two fresh secrets.

**Save your encryption key now.** Copy the `NEXUS_ENCRYPTION_KEY=` line from `.env` into
your password manager. Your finance, health, journal and account data are encrypted with
it, and backups don't include it. If you lose it, you lose that data, even with backups.

## 3. Start it

```powershell
docker compose up -d --build
```

- The first build takes 5–10 minutes. After that, NEXUS starts by itself whenever Docker
  Desktop starts.
- The first start also downloads the voice models (about 200 MB).

Then:

1. Open http://localhost:3000 and create your account. The first account becomes the
   owner, and sign-up then closes.
2. Open **Settings › System status**. Everything should say *Working* except the things
   you haven't set up yet. For anything that doesn't, the page says what to do.
3. Turn on two-factor sign-in under **Settings › Two-factor**.

## 4. Install the Windows app

1. Download `NEXUS_x.y.z_x64-setup.exe` from the latest release:
   https://github.com/TARUN-0514/infiops/releases/latest
2. Run it. It installs for your user only, so there's no admin prompt.

What the app adds:

- NEXUS in its own window, and a tray icon.
- Ctrl+Shift+Space for push-to-talk from any app.
- Windows notifications.
- The local agent, started with the app (step 6).

When a new version is out, you get a notification. Choose **Install update** in the tray
menu when it suits you. NEXUS never updates without you, and it installs only updates
signed with the project's key.

## 5. Use it on your phone

- **At home:** with your phone on the same Wi-Fi, open `http://YOUR-PC-IP:3000`. To find
  the IP, run `ipconfig` and look for the IPv4 address. Chat, tasks and everything else
  work.
- **Installing it as an app, notifications, and use away from home:** phones need HTTPS
  for these. Follow [DEPLOYMENT.md](DEPLOYMENT.md) to serve NEXUS privately over HTTPS
  with Tailscale. This is free, and nothing is opened to the internet.

## 6. Connect the rest (each optional)

Each item below has a section in the [README](../README.md):

| What | Where |
| --- | --- |
| Email and calendar (Google) | README › Connect Google |
| Wake word, hands-free voice, computer control | README › Voice, README › Computer control |
| Private web search for research | `docker compose up -d search` |
| Nightly backups | `docker compose up -d backup`, then README › Backups |
| Cloud model for very hard tasks | README › quick start, "Optional cloud" |

## 7. Check it once a month

- Run `scripts\restore-drill.sh` from Git Bash. It proves your latest backup restores,
  and the status page shows when it last passed.
- Copy the `backups` folder to another drive or a cloud folder.

## When something isn't working

Start at **Settings › System status**. It checks every part with a real call and says
what to do. Common fixes:

| What you see | Fix |
| --- | --- |
| Local AI model: can't reach | Start Ollama or LM Studio, and check the model was pulled |
| Background worker: not working | `docker compose up -d worker`, then `docker compose logs worker` |
| Email and calendar sync: reconnect | Settings › Integrations › Connect Google (Google test apps ask every 7 days) |
| Backups: none or failed | `docker compose up -d backup`, then `docker compose logs backup` |
| The page doesn't load at all | Check Docker Desktop is running, then run `docker compose ps` |

Logs for any part: `docker compose logs -f api` (or `worker`, `web`, `backup`).
