# Phase 2: email, calendar, knowledge base and briefing

## Decisions

- **Google scopes (chosen by Tarun, 2026-11-21):** `gmail.readonly`, `gmail.compose` and `calendar.events`, plus `openid` and `email`. NEXUS can read mail, write drafts and change calendar events. It cannot delete mail, change labels or touch settings. `gmail.compose` is what lets it send a draft, and every send waits for Tarun's approval.
- **Everything stays local.** Triage, summaries, drafts, document Q&A and the briefing run on the local model. Email bodies and documents are wrapped as untrusted data in every prompt.
- **Document parsing uses small libraries** (pypdf, python-docx, openpyxl, python-pptx) instead of Docling. They install in seconds, need no GPU or model download, and cover the formats in the spec. Images are described by a local vision model when `NEXUS_LOCAL_MODEL_VISION` is set (for example `qwen2.5vl:7b`). Docling can replace the parsers later if scanned PDFs need OCR.
- **Briefing audio uses the browser's speech for now.** Piper arrives with the voice work in Phase 3 and will replace it.
- **Push notifications** use standard Web Push (VAPID). Browsers allow it only on `https://` or `localhost`, so on a phone it works once NEXUS is served over HTTPS (Phase 3 desktop/PWA work, or a tunnel such as Tailscale).
- **Document parsing runs as a background task** in the API process, so uploads work even when the worker isn't running.

## Tasks

- [x] Migration 0003: connected accounts (encrypted tokens), sync logs, email messages (full-text search) and drafts, calendar events, documents and chunks (pgvector HNSW), work log, briefings, notifications, push subscriptions
- [x] Google OAuth with PKCE. An account shows as *connected* only after a real Gmail and Calendar call succeeds; a missing scope or failed call shows the error
- [x] Email: sync (last 14 days, every 10 minutes), local triage (priority, needs reply, one-line summary), views (inbox, needs reply, important, sent, all), search, drafts written by NEXUS, follow-ups. **Send creates an approval request; nothing is sent until it is approved.** Rejecting puts the draft back
- [x] Calendar: sync, day, week and month views, conflicts, free slots, time blocking from a task, create/edit/delete (written back to Google when connected). Changes from the assistant need approval
- [x] Knowledge base: upload PDF, DOCX, XLSX, PPTX, text, Markdown, CSV, transcripts (VTT/SRT) and images; chunking with page/slide/sheet labels; hybrid full-text + vector search; Q&A with numbered citations
- [x] Work log (completed tasks are logged automatically) and the weekly status report
- [x] Morning briefing built from real data only (calendar, emails needing a reply, tasks, overdue items): text, Listen (speech), history, settings for time and days, notification and Web Push
- [x] 13 assistant tools with risk levels: email send is irreversible (always asks), calendar changes are sensitive (ask), drafts are draft-level, searches are read
- [x] Web: Emails, Calendar, Knowledge Base, Work, Briefing, Settings › Integrations, notification bell, Home cards for schedule and inbox
- [x] Tests: 77 API tests (Google calls against a recorded fake), 27 web unit tests, browser run of every page at desktop and phone width

## Gate

1. **Tarun uses the morning briefing every day for a week.** Needs real use; it can't be tested in CI. The briefing is generated between the chosen time and three hours after, and appears on Home, the Briefing page and as a notification.
2. **No email is sent without approval.** Covered by tests: the send tool is irreversible so the permission engine always pauses it, an owner policy cannot set it to *allow*, the Send button only creates an approval, and the Gmail send call happens only inside the approval decision.

## Not yet verified

- **Real Google and the real local model have not been exercised.** The build environment can't reach Google or download model weights. Tests use a recorded fake of the Gmail and Calendar APIs and a scripted model. The first real check is connecting your Google account in Settings › Integrations.

## Left for later

- Piper voice for the briefing (Phase 3).
- OCR for scanned PDFs (Docling or a vision pass per page).
- Weather on Home and the briefing: needs an outside service, so it's not added without asking.
- Gmail push (Pub/Sub) instead of polling every 10 minutes.
