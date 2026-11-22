# Running NEXUS every day

NEXUS is built to run on your own PC, all the time. This guide covers four things:

- Keeping it running.
- Reaching it safely from your phone anywhere.
- Upgrading it.
- What to watch.

Start with [SETUP.md](SETUP.md) if NEXUS isn't installed yet.

## What runs where

| Part | Where | Port |
| --- | --- | --- |
| Web app (`web`) | Docker | 3000, the address you open |
| API (`api`) and worker (`worker`) | Docker | 8000 (API) |
| Postgres, Redis, MinIO | Docker | this PC only (127.0.0.1) |
| Voice (`voice`), search (`search`) | Docker | inside Docker only (search on 127.0.0.1:8888) |
| Backups (`backup`) | Docker | writes `./backups` |
| Local model (Ollama or LM Studio) | Windows | 11434 or 1234 |
| Windows app and local agent | Windows | connects out to the API |

Every container restarts by itself (`restart: unless-stopped`). With Docker Desktop set
to start when you sign in, NEXUS comes back after a reboot. Ollama starts with Windows by
default. LM Studio needs "Start server on launch" turned on.

## Reach it from your phone, privately (HTTPS)

Phones only install web apps, send push notifications and use the microphone over HTTPS.
The safe way to get HTTPS is Tailscale. It's free for personal use, and it connects your
phone and PC directly, so no port is opened to the internet.

Never forward ports on your router to NEXUS. It holds your email, calendar and finances.

1. Install Tailscale on the PC and the phone (https://tailscale.com/download). Sign in to
   the same account on both.
2. In the Tailscale admin console, open DNS and turn on **MagicDNS** and **HTTPS
   Certificates**.
3. On the PC, run this in PowerShell:
   ```powershell
   tailscale serve --bg 3000
   ```
   NEXUS is now at `https://YOUR-PC.YOUR-TAILNET.ts.net`, reachable only from your own
   devices.
4. Edit `.env`. Replace the placeholders with your PC's address, which `tailscale serve`
   prints:
   ```
   NEXUS_ENV=production
   NEXUS_COOKIE_SECURE=true
   NEXUS_PUBLIC_WEB_URL=https://YOUR-PC.YOUR-TAILNET.ts.net
   NEXUS_CORS_ORIGINS=["https://YOUR-PC.YOUR-TAILNET.ts.net"]
   ```
5. In Google Cloud, add the new redirect URI:
   `https://YOUR-PC.YOUR-TAILNET.ts.net/api/v1/integrations/google/callback`.
6. Apply the changes:
   ```powershell
   docker compose up -d
   ```
7. On the phone, open the address and choose **Add to Home Screen**. Then turn on
   notifications in Settings › Integrations.

With `NEXUS_ENV=production`, the interactive API docs are turned off and sign-in cookies
are sent only over HTTPS. Use the `ts.net` address from then on, on the PC as well.

## Upgrading

```powershell
cd infiops
docker compose exec backup /scripts/backup.sh   # a fresh backup first
git pull
docker compose up -d --build
```

The API applies database migrations itself when it starts (`alembic upgrade head`). Then
open **Settings › System status** to check everything is working.

To go back to an older version, check out that version and restore the backup you made
before upgrading. See README › Backups.

The Windows app updates separately, from the tray, when a new release is published. See
[RELEASING.md](RELEASING.md).

## What to watch

**Settings › System status** is the one place to look. It checks:

- The database and Redis.
- The worker's heartbeat, and each scheduled job's last run.
- The local model.
- Email and calendar sync.
- Automation runs.
- Server errors and slow requests.
- Backups, and when the restore drill last passed.
- Disk space.

If a check fails twice in a row (about ten minutes), you get a notification, and another
when it recovers. While something is broken, a banner shows on every page.

Every request is logged as one line of JSON, and slow ones are logged as `slow_request`:

```powershell
docker compose logs -f api
docker compose logs --since 1h api | Select-String slow_request
```

## Backups

See README › Backups for the commands.

- The `backup` service makes one backup every night, keeps 14, and catches up if the PC
  was off.
- Run the restore drill once a month.
- Keep a copy of `./backups` off the PC, and your encryption key in a password manager.

## Security checklist

- [ ] Two-factor sign-in on (Settings › Two-factor).
- [ ] `NEXUS_ENCRYPTION_KEY` saved in a password manager.
- [ ] Reached from outside only through Tailscale, never through port forwarding.
- [ ] `NEXUS_ENV=production` and `NEXUS_COOKIE_SECURE=true` once you use HTTPS.
- [ ] Cloud model off unless you need it (`NEXUS_CLOUD_ENABLED=false`). Secret data
      never goes to it either way.
- [ ] Backups running, and the restore drill passed this month.
