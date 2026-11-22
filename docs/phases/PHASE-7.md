# Phase 7: hardening and release

Ships in three pull requests:

1. **Security:** review of every sensitive and irreversible tool, a prompt-injection test
   suite, and agent evals.
2. **Operations:** monitoring and alerts, performance tuning, and a backup and restore
   drill.
3. **Release:** Windows installer and auto-update, deployment guide, API docs,
   `.env.example` and setup guide.

## Gate: one month of daily use with no manual fixes

This needs a month of real use after release, so it stays open until then.

## Part 1 tasks

- [x] Review each sensitive and irreversible tool: [SECURITY-REVIEW.md](../SECURITY-REVIEW.md)
- [x] Pin the risk table in a test, and check hard limits on permission policies
- [x] Audit every run, denial and approval request of sensitive tools on every path
- [x] Approval cards name what they touch (recipients, task, event, memory)
- [x] Lock a draft while its send waits; unlock when the request expires
- [x] `untrusted.neutral` on every prompt wrapper, plus a static test for new ones
- [x] Validate tool input before asking for approval
- [x] Prompt-injection suite: 15 tests
- [x] Agent evals: 11 scenarios in `services/api/evals/scenarios.json`, replayed from
      recordings in CI and run live against the local model with `python -m evals.run`
- [x] Tests: 210 API tests

## Part 1 notes

- **Live evals need their own database** whose name ends in `_eval`; the runner clears it
  between scenarios and refuses any other database. `--record` saves the local model's
  passing answers as the new recordings.
- Chat messages now include each tool call's input, so evals (and the UI later) can see
  exactly what the model asked for.

## Part 2 tasks

- [x] Measure the busiest endpoints with about a year of data (`services/api/scripts/perf.py`:
      6,000 tasks, 30,000 emails, 3,000 events, 4,000 work logs, 8,000 notifications)
- [x] Partial indexes for unread, untriaged, awaiting-reply and important email, completed
      tasks and notifications (migration 0010)
- [x] `GET /status`: database, Redis, worker heartbeat, scheduled jobs, local model, sync,
      automations, request errors and slow requests, backups and disk space, each with
      what to do
- [x] Worker heartbeat and per-job outcome in Redis; slow and failed requests logged and
      counted per hour (`NEXUS_SLOW_REQUEST_MS`, default 1,500)
- [x] Alerts: `monitor_tick` every five minutes notifies after two failed checks in a row,
      once, and again when it recovers
- [x] Nightly backup service: database dump and uploads, checksums, exact row counts from
      the dump's own snapshot, catch-up when the PC was off at backup time, 14 kept
- [x] Restore drill: `scripts/restore-drill.sh` restores into a scratch database and runs
      `python -m app.cli restore-check` (counts, schema revision, decryption)
- [x] Settings, then System status page, and a banner on every page while something is broken
- [x] Tests: 217 API tests (7 new, including the real backup and restore scripts), 85 web tests

## Part 2 performance (median of five calls, perf data set)

| Endpoint | ms |
| --- | --- |
| /tasks?status=todo | 8.7 |
| /tasks/today | 8.6 |
| /email/summary | 22.6 |
| /email/messages?limit=50 | 12.0 |
| /notifications | 9.7 |
| /insights | 30.6 |
| /analytics?days=30 | 33.0 |
| /analytics?days=90 | 50.2 |
| /briefings/today | 4.3 |
| /approvals?status=pending | 6.2 |
| /status | 18.3 |

Everything was already under 60 ms; the indexes keep the email and notification lists flat
as they grow instead of scanning every row.

## Part 2 notes

- **The encryption key is not in backups.** Keep a copy of `.env` (or at least
  `NEXUS_ENCRYPTION_KEY`) in a password manager. The restore drill fails loudly if the key
  can't read the backup.
- Backups land in `./backups` on the PC. Copying that folder to another drive or a cloud
  folder is up to the owner; NEXUS doesn't upload anything.
- The worker check is left out of alerts because the worker sends them; the banner
  covers it.

## Part 3 tasks

- [x] Windows installer: NSIS, per-user (no admin prompt), Start menu folder
- [x] Auto-update: release builds check signed GitHub releases at start and every six
      hours, notify once per version, and install only when the owner chooses
      **Install update** in the tray; signatures must name the version
      (`requireSignedVersion`), so an older release can't be replayed as newer
- [x] `desktop-release` workflow: tag `desktop-vX.Y.Z`, build, sign, draft release with
      `latest.json`; nothing reaches installed apps until the draft is published
- [x] Guides: [SETUP.md](../SETUP.md), [DEPLOYMENT.md](../DEPLOYMENT.md),
      [RELEASING.md](../RELEASING.md), [API.md](../API.md) with `api/openapi.json`
- [x] API reference generated from the code; a test fails when it's out of date
- [x] `.env.example` documents every setting; a test checks it against the settings
      model and that its values parse
- [x] Compose: Postgres, Redis and MinIO bound to 127.0.0.1; every service restarts by itself

## What is not automated

- **The release signing key** is made once on the owner's PC and stored as a GitHub
  secret (RELEASING.md). Until it exists, the release workflow stops with a clear error
  and installed apps simply don't check for updates.
- **The Windows installer is built only on GitHub's Windows runners.** CI here checks the
  Rust code with clippy on Linux, with and without the updater config, but the first real
  installer and update will be tried on the owner's PC.
- **HTTPS for the phone** uses Tailscale, set up by hand (DEPLOYMENT.md).
- **The gate** (one month of daily use with no manual fixes) starts when the owner starts
  using it daily.
