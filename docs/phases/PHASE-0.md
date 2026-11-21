# Phase 0: Foundation (weeks 1-2)

Gate: the owner can sign in on web and phone, CI is green, and `docker compose up` starts everything.

## Tasks
- [x] Monorepo layout, blueprint and engineering rules (`docs/BLUEPRINT.md`, `CLAUDE.md`)
- [x] API skeleton: FastAPI, settings from env, JSON logs with request IDs, security headers, `/healthz`, `/readyz`
- [x] Database: SQLAlchemy models + Alembic migration 0001 (users, user_preferences, user_sessions, devices, audit_logs)
- [x] Auth: owner registration (closes after first user), argon2id, login, TOTP two-factor with replay protection,
      short-lived access JWT, rotating refresh token in an httpOnly cookie, reuse detection, CSRF double-submit,
      session list and revoke, rate limits, audit log
- [x] Worker: Arq with a nightly expired-session purge
- [x] Docker Compose: Postgres + pgvector, Redis, MinIO, Ollama (optional profile), api, worker, web
- [x] Web app shell: Next.js, design system (dark first + light), 13-item navigation, sign-in, two-factor, sessions, PWA manifest
- [x] CI: lint, type-check, tests, build, dependency scan, Docker image builds

## Deferred on purpose
- Device pairing by QR moves to phase 3, when the desktop app exists.
- pgvector extension is enabled in the phase 1 migration, when memory tables arrive.

## Gate check
- [x] Register, sign in, reload (session restored), two-factor setup, theme switch, sign out: tested end to end in Chromium, desktop and Pixel 7 sizes
- [ ] CI green on GitHub
- [ ] `docker compose up --build` on the owner's machine
