# NEXUS AI Merged Blueprint

> **Update, 2026-11-21: local-first.** NEXUS now runs every AI job on the owner's PC by default (Ollama or LM Studio, Qwen3 14B Q4, bge-m3), at no cost. Cloud models are an optional per-message switch with a daily cap, for very hard tasks only. Where this document says a job uses a Claude model, read that as the cloud option. See docs/phases/PHASE-1.md and CLAUDE.md.

Version of Nov 21, 2026. Live doc with diagrams: https://claude.ai/artifact/9Dsijbp4XnNVHCEWj8fL1h

## Overview

NEXUS is one assistant with one memory and one command centre for your work and personal life. You use it by chat or voice, in the browser, on Windows and on your phone. This version takes the full feature scope, security rules and security workspaces from the NEXUS spec. From the Jarvis blueprint it takes the build order, the per-phase gates, versioned memory, local processing of private data, and a model gateway that works with more than one provider.

Final decisions:

| Topic | Decision | Taken from |
| --- | --- | --- |
| Scope | All 13 NEXUS modules, built in thin slices | NEXUS |
| Web app | Next.js + TypeScript, Tailwind, shadcn/ui, Framer Motion, Recharts | NEXUS |
| Windows desktop | Tauri 2 wrapping the same frontend, plus a local agent for voice, files and computer control | Both |
| Phone | PWA first; a native Expo app later only if background voice or health sync is needed | NEXUS first, Jarvis later |
| Backend | Python FastAPI, REST + WebSockets, Arq workers on Redis | Both |
| Data | PostgreSQL + pgvector, Redis, S3-compatible object storage | Both |
| AI | Model gateway that supports more than one provider: Claude for agents, coding and computer control; OpenAI Realtime or local voice; local embeddings; Ollama for private data | Merged |
| Agent framework | Plain tool loops with database-saved runs first; LangGraph added for the automation studio | Merged |
| Memory | Four types (working, episodic, semantic, procedural), each with source, confidence, privacy label and version history | Merged |
| Security | NEXUS rule set, plus risk levels on every tool enforced in code | Merged |
| Roadmap | 8 phases (0 to 7) over about 24 weeks, each with a gate you check yourself; something you use daily by week 6 | Jarvis order, NEXUS content |

The central rule from NEXUS stays: this is an AI operating system, not a set of separate productivity apps. Every module is something the assistant can read and act on through the same tools.

## Production architecture

The web app, Windows app and phone all use the same backend, the same memory and the same tools. The cloud backend runs the agents, the automation engine and the memory engine. The Windows app's local agent is the bridge to your computer: it handles voice, approved files, screen control and the local model for private data.

_Diagram: NEXUS production architecture · 3 surfaces, 5 cloud services, 5 data and AI services (see the live doc)._

The local agent connects outward to the cloud, so nothing on your PC is open to the internet. Jobs that need the PC, such as screen control or secret data, wait in a queue while it is off, and you get a notice.

Tech stack:

| Layer | Choice |
| --- | --- |
| Web frontend | Next.js + TypeScript, Tailwind CSS, shadcn/ui, Framer Motion, Recharts, TanStack Query |
| Desktop | Tauri 2 wrapping the web app, plus a Python local agent |
| Phone | Installable PWA; native Expo app later if needed |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, REST + WebSockets |
| Background jobs | Arq workers on Redis |
| AI | Model gateway (see AI layer); plain agent loops; LangGraph only for the automation engine |
| Database | PostgreSQL 16 + pgvector (Supabase or Neon in production) |
| Cache and queues | Redis 7 |
| Files | S3-compatible object storage (MinIO locally, Cloudflare R2 or S3 in production) |
| Document parsing | Unstructured or Docling, run locally |
| Browser and desktop automation | Playwright (isolated profile), allow-listed OS actions, Claude computer use |
| Voice | openWakeWord, OpenAI Realtime over WebRTC, or local faster-whisper + Piper |
| Infrastructure | Docker Compose for dev, one small VM or Fly.io/Railway in production, Tailscale between PC and cloud |
| Observability | Structured JSON logs, OpenTelemetry traces, health checks, Sentry for errors, cost dashboard |

## AI layer

Every AI call goes through one model gateway, which picks a model for each job. Changing which provider does a job means editing config, not code. If a provider fails, the gateway retries once and then moves the job to the fallback.

| Job | Primary | Fallback | Why |
| --- | --- | --- | --- |
| Orchestrator and planning | Claude Sonnet 5.5; Opus 5.5 for long multi-step plans | OpenAI flagship model | Strong at multi-step tool use |
| Intent routing, classification, memory extraction | Claude Haiku 5.5 | Local model on Ollama | Fast and cheap; works offline |
| Research and long reports | Claude Opus 5.5 | OpenAI flagship model | Deep reasoning with citations |
| Coding agent | Claude Opus 5.5, Claude Code on your PC | OpenAI flagship model | Repository-level coding |
| Computer control | Claude computer-use tool with Playwright | Playwright scripts only | Built-in screen control |
| Voice conversation | OpenAI Realtime API (speech to speech) | Local faster-whisper + Piper | Most natural voice; local is free and private |
| Embeddings for memory and documents | bge-m3 on Ollama (1024 dimensions) | Voyage or OpenAI embeddings | Memory never depends on one company |
| Private data (finance, health, anything marked secret) | Local model on Ollama only | None: if the local model is down, the job waits | Never leaves your machine unless you allow it |
| Document parsing (PDF, DOCX, XLSX, PPTX, images) | Unstructured or Docling locally, with vision model for images | Cloud vision model | Parsing stays local |

The gateway also tracks tokens and cost for every call, enforces a per-run and per-day budget, uses prompt caching, and times out slow calls.

### Memory engine

Memory is its own service, not just conversation history. It has four types.

| Type | What it holds | Lifetime |
| --- | --- | --- |
| Working | The current conversation and task context | Redis, cleared when the session ends |
| Episodic | Past conversations, events and activities, as summaries | Permanent, summarised daily and weekly |
| Semantic | Facts, preferences, people, decisions, knowledge | Permanent until superseded or deleted |
| Procedural | How you like things done, such as report format or email tone | Permanent, updated as you correct it |

Rules for every memory:

- It carries a source, a confidence score, a timestamp and a privacy label.
- It is never edited in place. A new version supersedes it and the old one keeps its history.
- Something the AI infers is stored as "inferred" and confirmed with you before it counts as a fact.
- Conflicts and duplicates are flagged for you to resolve.
- You can browse, correct, export and delete any memory. Memory policies let you turn extraction off by category.
- The assistant never claims to remember something that isn't stored, and it shows the source when it uses a memory.

How memories are retrieved for each request:

1. Rewrite the request into a search query, using the current conversation.
2. Run vector search and full-text search together, filtered by privacy rules.
3. Rank the results by relevance, importance, recency and confidence.
4. Add the best 10 to 15 memories to the prompt, with their sources.
5. After the reply, the memory agent extracts new facts and asks for confirmation where needed.

### Voice pipeline

- Push-to-talk works everywhere. Hands-free and the "Hey NEXUS" wake word work on the desktop app and are off until you enable them, with a visible microphone indicator.
- Voice uses the same orchestrator and tools as chat, not a separate chatbot.
- Streaming in both directions, with voice activity detection. You can interrupt mid-answer.
- Wake word uses openWakeWord locally. Speech uses OpenAI Realtime over WebRTC, or local Whisper and Piper if you choose private mode.

## Feature breakdown

All 13 NEXUS modules are in scope. Each one ships an MVP in the phase shown, and its later features follow once the MVP passes its gate. Every feature needs a working UI, an API, database storage, validation, error handling and tests. Placeholder buttons don't count.

| # | Module | MVP | Later | Phase |
| --- | --- | --- | --- | --- |
| 1 | Command centre (Home) | Greeting, date, weather, today's schedule, pending and overdue tasks, important emails, the "Ask NEXUS" command bar | Widgets you can drag, resize, hide and create; compact and expanded layouts; productivity score; focus timer; goals and habits widgets | 1, then 3 |
| 2 | Memory and personal intelligence | Fact extraction with consent, semantic search, memory browser to edit and delete, sources on answers | Conflict and duplicate detection, expiry, daily and weekly summaries, people and relationship graph (personal CRM), export | 1, then 4 |
| 3 | AI chat assistant | Multi-turn chat with tools, history and search, file uploads, writing and summaries | Data analysis on uploads, decision support, image understanding | 1 |
| 4 | Tasks and projects | Tasks from natural language (title, due date, priority, category, reminder), subtasks, projects, list and kanban views, recurring tasks | Dependencies, attachments, calendar view, time blocking from tasks | 1, then 3 |
| 5 | Email and calendar | Gmail and Google Calendar: triage, summaries, drafts, pending replies, follow-up reminders, day, week and month views, conflict detection, free-slot finder | Outlook and Microsoft Calendar, meeting prep packs, smart scheduling, "remind me if no reply in 3 days" | 2 |
| 6 | Knowledge base | Upload PDF, DOCX, XLSX, PPTX, images, text and transcripts; parsing; vector and full-text search; Q&A with citations | Auto-categories, related documents, version tracking, comparing two documents, Google Drive and Notion sync | 2 |
| 7 | Voice (JARVIS mode) | Push-to-talk on web, desktop and phone; spoken replies; interruption | Wake word and hands-free on desktop, continuous conversation, voice picker | 3 |
| 8 | Computer and browser automation | Open apps, files and URLs; folder actions in approved folders; browser tasks in an isolated profile; execution log | Screen control through computer use, recorded desktop workflows, watch-folder triggers | 4 |
| 9 | Research and coding agent | Web research with citations that separates verified facts, assumptions and opinions; PDF analysis; GitHub PR and issue summaries | News and topic monitoring, saved articles, code review and debugging on your repos with Claude Code | 4 |
| 10 | Work productivity | Work log, meeting notes to tasks, follow-up tracker, weekly status report, email drafts in your tone | Security workspaces (below), workload analysis, issue tracking | 2, then 5 |
| 11 | Personal life, finance and fitness | Goals, routines, important dates, lists, journal; income and expenses by hand, voice or CSV; budgets; EMIs and bills; workouts with sets, reps and weight; body weight, water, sleep, calories and protein; habits | Debt planner, savings goals, cash-flow view, credit cards and loans; exercise library, progress photos, weekly fitness report; travel planning, reading list | 5 |
| 12 | Automation studio | Routines in natural language with schedule and event triggers, conditions, approval checkpoints, run history, retries and failure alerts | Visual workflow builder, external API steps, shared templates | 6 |
| 13 | Analytics and proactive intelligence | Morning briefing (text and audio); overdue and deadline alerts | Midday check-in, evening review, weekly and monthly reports, procrastination and overload patterns, finance and fitness trends; only from real data, never invented | 2, then 6 |

Security workspaces for your job (module 10, phase 5):

- **Vulnerability management:** findings from Amazon Inspector, GHAS and DAST scans, Guardium activities, SLA and aging, escalations, remediation follow-ups.
- **AppSec, cloud security and pentest projects:** configurable boards with their own fields and workflows.
- **Learning workspace:** OSCP preparation with a syllabus tracker, lab log, notes and spaced review.

Shared across all modules:

- **Notification centre:** in-app, browser, email and phone push, with settings per type and quiet hours.
- **Approval centre:** one queue for every action waiting on you, with approve, edit and reject.
- **Integrations page:** connected services, status, permissions, last sync, available actions and disconnect. Planned connections: Gmail, Google Calendar and Drive, Outlook, Notion, Slack, Telegram, GitHub, weather and web search.
- **Settings:** profile, AI model and personality, memory controls, voice, theme (dark first, light available), notifications, privacy, data export and deletion, backup and restore, security.

## Agent design

One orchestrator talks to you and delegates to 12 specialist agents. Each specialist only gets the tools it needs. Specialists never talk to you directly or call each other. They return results to the orchestrator, which checks them, cites sources and asks for approvals.

| Agent | Responsibilities | Tools |
| --- | --- | --- |
| Orchestrator | Understands intent, makes a bounded plan, delegates, validates results, replies | delegate, memory.search, approval.request, notify |
| Router | Tags intent, urgency and needed agents in under 300 ms so simple requests skip planning | none (structured output) |
| Memory | Retrieves, extracts, confirms, supersedes and summarises memories | memory.*, entity.* |
| Work | Tasks, projects, work log, reports, security workspaces | tasks.*, projects.*, workspace.*, notion.* |
| Email | Search, triage, summarise, draft, follow-ups | gmail.*, outlook.* |
| Calendar | Events, free slots, conflicts, time blocking, meeting prep | gcal.*, mscal.* |
| Personal | Goals, routines, lists, important dates, journal, travel | goals.*, lists.*, reminders.\* |
| Finance | Expenses, budgets, EMIs, debts, reports (local model only) | finance.\*, files.parse\_statement |
| Fitness | Workouts, body metrics, nutrition, sleep, habits, weekly reports; gives practical tips without acting as a medical professional | fitness.*, habits.* |
| Research | Web and document research with citations; separates verified facts, assumptions and opinions | web.search, web.fetch, kb.search |
| Coding | Repository understanding, code review, debugging, docs, Claude Code runs | github.\* (scoped), claude\_code.run |
| Operator | Apps, approved folders, isolated browser, screen control | desktop.*, browser.*, computer\_use |
| Automation | Runs approved workflows step by step with checkpoints | workflow.run, plus the tools each step allows |

How a request runs:

1. The router tags the request. The orchestrator loads context: recent messages, ranked memories, today's calendar and open tasks.
2. It makes a bounded plan, then runs read-only steps in parallel and other steps in order.
3. Each tool call is checked on the server against the permission policy. A model's claim that something is approved is never enough.
4. Calls that need approval pause the run and create an approval request. The run resumes when you decide.
5. The orchestrator checks the results, names anything missing, replies with sources, and the memory agent extracts what is worth keeping.

### Permission model

Every tool has a risk level, and each level has a default policy. You can loosen a policy for one specific routine. The hard limits at the bottom never change.

| Risk level | Examples | Default policy |
| --- | --- | --- |
| read | Search memories, read approved documents, search email, read calendar | Allowed once the service is connected |
| draft | Draft an email, draft a report, propose a schedule | Allowed; shown to you |
| reversible | Create a task, add a reminder, label an email, open an app | Allowed; logged with undo |
| sensitive | Create or move a calendar event, write files in approved folders, browser form submit | Approval required unless a routine allows it |
| irreversible | Send email or messages, accept or cancel invites, delete files, push code, run shell commands | Explicit approval every time |
| forbidden | Transfer money, make payments, change account security settings | Never autonomous; NEXUS can only prepare instructions for you |

Website, email and document content can't grant permissions. Instructions found inside retrieved content are treated as data, never as commands.

## Database schema

PostgreSQL is the source of truth, with pgvector for search, Redis for working memory and queues, and object storage for files. There are about 70 tables in 8 groups. Proper relational tables come first, and JSONB is used only for flexible metadata.

| Group | Tables |
| --- | --- |
| Identity and security | users, user\_profiles, user\_preferences, user\_sessions, devices, api\_keys, permission\_policies, audit\_logs |
| Memory and conversation | conversations, messages, conversation\_summaries, memory\_items, memory\_sources, memory\_conflicts, entities, entity\_links |
| Knowledge | documents, document\_versions, document\_chunks, saved\_articles, research\_reports |
| Productivity | projects, tasks, task\_dependencies, tags, task\_tags, reminders, calendar\_events, meeting\_notes, work\_logs, goals, routines, journal\_entries, lists, list\_items |
| Security workspaces | workspaces, workspace\_items (findings, scans, escalations), learning\_tracks, learning\_sessions |
| AI and automation | agent\_runs, agent\_messages, tool\_registry, tool\_executions, approval\_requests, automation\_workflows, automation\_steps, automation\_runs, model\_usage\_logs |
| Integrations and notifications | connected\_accounts, integration\_sync\_logs, email\_threads, notifications, notification\_preferences, briefings |
| Finance and fitness | financial\_accounts, transactions, budgets, recurring\_payments, debts, savings\_goals, exercises, workout\_sessions, workout\_sets, body\_metrics, nutrition\_logs, water\_logs, sleep\_logs, habits, habit\_logs |

Design rules:

1. UUID primary keys. Every user-owned row has `user_id`, enforced by row-level security as a second layer.
2. Timestamps stored in UTC and shown in your time zone (Asia/Kolkata).
3. Indexes on `user_id`, `status`, `created_at` and common date filters.
4. Financial data, health data and integration tokens are encrypted at the column level.
5. Memories and documents are versioned, never overwritten. Embeddings record their model so they can be rebuilt.
6. Soft delete only where retention allows; a full "delete my data" removes everything.
7. Every sensitive action is written to `audit_logs`.
8. Daily backups, with a restore test every month.

SQL for the core tables that the rest depend on:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE NOT NULL,
  password_hash text NOT NULL,                 -- argon2id
  display_name text,
  timezone text NOT NULL DEFAULT 'Asia/Kolkata',
  role text NOT NULL DEFAULT 'owner',
  mfa_secret_enc bytea,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  channel text NOT NULL,                       -- chat, voice, briefing, automation
  title text, summary text,
  started_at timestamptz NOT NULL DEFAULT now(), ended_at timestamptz
);

CREATE TABLE messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('user','assistant','tool','system')),
  agent text, content jsonb NOT NULL,
  search tsvector, tokens int,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON messages USING gin (search);

CREATE TABLE memory_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  memory_type text NOT NULL CHECK (memory_type IN ('episodic','semantic','procedural')),
  category text NOT NULL,                      -- profile, preference, work, project, goal, person, decision, routine, conversation, knowledge
  content text NOT NULL,
  status text NOT NULL DEFAULT 'active',       -- inferred, active, superseded, expired, deleted
  confidence real NOT NULL DEFAULT 0.7,        -- 0 to 1
  importance smallint NOT NULL DEFAULT 3,      -- 1 to 5
  privacy text NOT NULL DEFAULT 'normal',      -- normal, private, secret (secret = local model only)
  embedding vector(1024), embedding_model text,
  supersedes uuid REFERENCES memory_items(id),
  valid_from timestamptz NOT NULL DEFAULT now(), valid_to timestamptz,
  expires_at timestamptz,
  last_used_at timestamptz, use_count int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON memory_items USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON memory_items (user_id, category) WHERE status = 'active';

CREATE TABLE memory_sources (
  memory_id uuid REFERENCES memory_items(id) ON DELETE CASCADE,
  source_type text NOT NULL,                   -- message, email, document, event, manual
  source_id text NOT NULL, quote text,
  PRIMARY KEY (memory_id, source_type, source_id)
);

CREATE TABLE memory_conflicts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_a uuid REFERENCES memory_items(id), memory_b uuid REFERENCES memory_items(id),
  kind text NOT NULL,                          -- duplicate, contradiction
  status text NOT NULL DEFAULT 'open', resolved_at timestamptz
);

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  title text, mime_type text, storage_key text NOT NULL,
  source text, external_id text, category text,
  current_version int NOT NULL DEFAULT 1, summary text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_chunks (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version int NOT NULL, ordinal int NOT NULL, page int,
  content text NOT NULL, search tsvector,
  embedding vector(1024), embedding_model text
);
CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON document_chunks USING gin (search);

CREATE TABLE projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  workspace_id uuid, name text NOT NULL, area text,  -- work, personal, learning
  status text NOT NULL DEFAULT 'active', due_at timestamptz
);

CREATE TABLE tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  project_id uuid REFERENCES projects(id),
  parent_task_id uuid REFERENCES tasks(id),    -- subtasks
  title text NOT NULL, notes text,
  status text NOT NULL DEFAULT 'todo',         -- todo, in_progress, blocked, done, cancelled
  priority smallint NOT NULL DEFAULT 3,
  category text, due_at timestamptz, remind_at timestamptz,
  recurrence text,                             -- RRULE
  source_type text, source_id text,            -- email, meeting, chat
  postponed_count int NOT NULL DEFAULT 0,      -- feeds procrastination analytics
  created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE INDEX ON tasks (user_id, status, due_at);

CREATE TABLE tool_registry (
  name text PRIMARY KEY,                       -- gmail.send, desktop.open
  agent text NOT NULL,
  risk text NOT NULL CHECK (risk IN ('read','draft','reversible','sensitive','irreversible','forbidden')),
  input_schema jsonb NOT NULL, runs_on text NOT NULL DEFAULT 'cloud'  -- cloud, desktop
);

CREATE TABLE permission_policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  tool_name text REFERENCES tool_registry(name),
  scope jsonb,                                 -- e.g. {routine_id, recipient_domain}
  decision text NOT NULL CHECK (decision IN ('allow','ask','deny'))
);

CREATE TABLE agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  conversation_id uuid REFERENCES conversations(id),
  automation_run_id uuid, parent_run_id uuid REFERENCES agent_runs(id),
  agent text NOT NULL, goal text, plan jsonb,
  status text NOT NULL,                        -- queued, running, waiting_approval, done, failed
  state jsonb,                                 -- checkpoint so a paused run can resume
  started_at timestamptz DEFAULT now(), finished_at timestamptz
);

CREATE TABLE tool_executions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES agent_runs(id),
  tool_name text NOT NULL REFERENCES tool_registry(name),
  input jsonb, output jsonb, error text,
  status text NOT NULL,                        -- pending_approval, running, done, failed, rejected
  device_id uuid, undo jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE approval_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  tool_execution_id uuid NOT NULL REFERENCES tool_executions(id),
  summary text NOT NULL, preview jsonb,
  status text NOT NULL DEFAULT 'pending',      -- pending, approved, edited, rejected, expired
  expires_at timestamptz, decided_at timestamptz
);

CREATE TABLE automation_workflows (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  name text NOT NULL, description text,
  trigger jsonb NOT NULL,                      -- {cron} or {event, filter}
  enabled boolean NOT NULL DEFAULT true,
  created_from_prompt text
);

CREATE TABLE automation_steps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id uuid NOT NULL REFERENCES automation_workflows(id) ON DELETE CASCADE,
  ordinal int NOT NULL, kind text NOT NULL,    -- agent, tool, condition, approval, notify
  config jsonb NOT NULL, retry_max smallint DEFAULT 3
);

CREATE TABLE automation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id uuid NOT NULL REFERENCES automation_workflows(id),
  status text NOT NULL, error text,
  started_at timestamptz DEFAULT now(), finished_at timestamptz
);

CREATE TABLE model_usage_logs (
  id bigserial PRIMARY KEY,
  user_id uuid, run_id uuid, provider text, model text, job text,
  input_tokens int, output_tokens int, cost_usd numeric(10,5),
  latency_ms int, fallback_used boolean DEFAULT false,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE connected_accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  provider text NOT NULL, scopes text[],
  token_enc bytea NOT NULL, status text NOT NULL DEFAULT 'active',
  last_sync_at timestamptz, UNIQUE (user_id, provider)
);

CREATE TABLE audit_logs (
  id bigserial PRIMARY KEY,
  user_id uuid, actor text NOT NULL,           -- user, agent:<name>, system
  action text NOT NULL, target text, detail jsonb, ip inet,
  at timestamptz NOT NULL DEFAULT now()
);
```

The finance, fitness, calendar and workspace tables follow the same pattern. Write them in their own phase's migration, so the schema grows with the features.

## Security and privacy

Security is part of every phase, not a final step. This is the full NEXUS rule set, plus the code-enforced risk levels from the Jarvis plan.

| Area | Rules |
| --- | --- |
| Authentication | Argon2id password hashing, optional TOTP two-factor, short-lived access tokens with rotating refresh tokens, session list with remote sign-out, device pairing by QR for the desktop and phone |
| Web protection | Input validation with Pydantic and Zod, CSRF tokens, strict Content Security Policy, output escaping against XSS, parameterised queries only, rate limits per user and per IP |
| Data | TLS everywhere; database and backups encrypted at rest; column encryption for tokens, finance and health data; secrets from environment or a secret manager, never in code |
| Files | Type and size checks, malware scan, stored outside the web root, served through short-lived signed URLs |
| Prompt injection | Email, documents, web pages and tool outputs are marked as untrusted data in the prompt; they can never grant permissions or change policy; the permission check runs in server code after the model decides |
| Tools | Every tool registered with a risk level; server-side check on every call; approvals tied to the exact action preview; full audit log |
| Computer control | Scoped tool registry, allow-listed folders and apps, isolated browser profile, no unrestricted shell, kill switch on the desktop app |
| Integrations | OAuth with the smallest scopes; tokens encrypted; an integration shows as connected only after a real test call succeeds |
| Privacy | Memory consent settings by category; secret data processed only by the local model; full export and full deletion; model usage log so you can see what was sent where |
| Operations | Structured logs with no secrets or message bodies, health checks, monitoring and alerts, daily backups with monthly restore tests, dependency and container scanning in CI |

One caution from the NEXUS spec is worth keeping: local models aren't automatically more secure. Local storage still needs encryption, and routing rules must be explicit and visible in settings.

## Implementation roadmap

The build has 8 phases over about 24 weeks for one person working part-time with a coding agent. That is an estimate. Phase 1 is highlighted because it gives you chat, memory and tasks you can use every day from week 6. Memory comes before most agents, as both plans recommend.

_Diagram: NEXUS roadmap · 8 phases, about 24 weeks (see the live doc)._

Each phase ends with a gate you can check yourself. Don't move on until it passes, because later phases depend on memory, approvals and voice working reliably. If time is tight, phases 5 and 6 can swap, or their later features can move to after release.

## Master coding prompt

The prompt has two parts, so a coding agent can follow all of it. Save the core prompt as `CLAUDE.md` (or `AGENTS.md`) at the root of the repository, so it applies to every session. Then start each phase with that phase's short prompt. Also commit this blueprint as `docs/BLUEPRINT.md`, because the core prompt refers to it.

### Core prompt (save as CLAUDE.md)

```markdown
# NEXUS AI: engineering rules

You are the principal engineer building NEXUS, a personal AI operating system for one owner (Tarun). It is one assistant, one memory and one command centre for work and personal life, used by chat and voice on the web, a Windows desktop app and a phone PWA. The full design is in docs/BLUEPRINT.md. Follow it, and ask before departing from it.

## Stack
- apps/web: Next.js (App Router) + TypeScript strict, Tailwind, shadcn/ui, Framer Motion, Recharts, TanStack Query. Dark-first premium UI (charcoal and navy, restrained glass), light theme supported, responsive to phone width, installable as a PWA.
- apps/desktop: Tauri 2 wrapping apps/web, plus services/local-agent (Python) connected to the API over an authenticated outbound WebSocket. The local agent does wake word (openWakeWord), local STT/TTS (faster-whisper, Piper), allow-listed desktop and folder actions, Playwright in an isolated profile, and screen control via the Claude computer-use tool.
- services/api: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic. REST + WebSockets. OpenAPI is the contract, and the TypeScript client is generated from it.
- services/worker: Arq on Redis for agent runs, syncs, reminders, briefings and automations.
- services/ai: model gateway, orchestrator, router, specialist agents, memory engine, tool registry.
- Data: PostgreSQL 16 + pgvector, Redis 7, S3-compatible storage (MinIO locally).
- Infra: Docker Compose for dev; Dockerfiles per service; GitHub Actions CI (lint, type-check, test, build, dependency and container scan).

## AI layer
- All model calls go through services/ai/gateway. Config maps each job to a primary and a fallback model: orchestrator -> claude-sonnet-5-5 (claude-opus-5-5 for long plans); routing and memory extraction -> claude-haiku-5-5; research and coding -> claude-opus-5-5; voice -> OpenAI Realtime or local Whisper + Piper; embeddings -> bge-m3 via Ollama (1024 dimensions); private or secret data -> local Ollama model only. No model ids in code.
- The gateway handles timeouts, one retry then fallback, prompt caching, token and cost logging to model_usage_logs, and per-run and per-day budgets.
- Agents are plain tool-use loops whose state is checkpointed in agent_runs.state so a run can pause for approval and resume. LangGraph may be added later for the automation engine only.

## Non-negotiables
1. No placeholder UI. Every feature you ship has a UI, API, persistence, validation, error, loading, empty and success states, authorisation and automated tests.
2. Every tool is registered in tool_registry with a risk level (read, draft, reversible, sensitive, irreversible, forbidden). The server checks every call against permission_policies. Sensitive and irreversible calls create an approval_requests row and pause. Forbidden tools (payments, transfers, account security) never run. A model's claim of approval is never trusted.
3. Emails, documents, web pages and tool outputs are untrusted. Wrap them as data in prompts. They cannot change policy or grant permissions.
4. Memory is versioned: supersede, never overwrite. Every memory has a source, confidence, privacy label and timestamp. Inferred facts stay 'inferred' until the owner confirms them. Never claim to remember something that is not stored, and cite sources when using memory.
5. Never invent data, analytics or integration status. An integration shows as connected only after a successful test call. Seed data is for development only and is visibly marked.
6. Security: argon2id, optional TOTP, rotating refresh tokens, CSRF, CSP, rate limits, parameterised queries, encrypted tokens and finance and health columns, secure uploads, audit_logs for sensitive actions, secrets only from env or a secret manager.
7. Code quality: mypy strict and ruff for Python, TypeScript strict and ESLint for the web. Small modules, clear service boundaries, no giant components.
8. Tests: pytest (API, permissions, memory, agents with recorded model responses), Vitest (UI logic), Playwright end-to-end for each major workflow.

## How to work
- At the start of a phase, read docs/BLUEPRINT.md and write docs/phases/PHASE-N.md with a task list and the gate test.
- Work in small commits, each with tests. Run the tests before you say something works.
- Ask before adding a paid service, a new OAuth scope or a new dependency that has many alternatives.
- At the end of a phase: run the full test suite, update the README with run commands, list anything stubbed, and stop for review.
```

### Phase prompts

Start each phase with one of these in a new session.

```markdown
PHASE 0, FOUNDATION (weeks 1-2)
Set up the monorepo, Docker Compose (Postgres + pgvector, Redis, MinIO, Ollama), the FastAPI skeleton with health checks and structured logging, Alembic with the identity, security and audit tables, authentication (register, login, TOTP, sessions, refresh rotation), the Next.js shell with the 13-item navigation and design system, the generated API client, and CI. Gate: I can sign in on web and phone, CI is green, and docker compose up starts everything.
```

```markdown
PHASE 1, AI CORE, MEMORY, CHAT AND TASKS (weeks 3-6)
Build the model gateway, router, orchestrator and memory agent; the tool registry, permission engine and approval centre; chat over WebSocket with streaming, history, search and file upload; the memory engine with extraction, consent, hybrid retrieval, sources and the memory browser; tasks and projects with natural-language creation, subtasks, recurrence, list and kanban views; the Home page with greeting, weather, tasks and the Ask NEXUS command bar. Gate: NEXUS remembers facts across sessions with sources, and creates tasks correctly from 20 test sentences.
```

```markdown
PHASE 2, EMAIL, CALENDAR, KNOWLEDGE BASE, BRIEFING (weeks 7-10)
Add Google OAuth with minimal scopes and test calls; Email agent (triage, summaries, pending replies, drafts, follow-ups; sending needs approval); Calendar agent and calendar views (day, week, month, conflicts, free slots, time blocking; changes need approval); knowledge base (upload and parse PDF, DOCX, XLSX, PPTX, images and transcripts, hybrid search, Q&A with citations); work log and weekly status report; the morning briefing as text and audio with a push notification. Gate: I use the morning briefing every day for a week, and no email is sent without my approval.
```

```markdown
PHASE 3, VOICE AND DESKTOP (weeks 11-13)
Build the Tauri Windows app and the local agent; push-to-talk on web, desktop and PWA; streaming voice with interruption using the same orchestrator and tools; optional wake word and hands-free mode on desktop with a visible mic indicator; the customisable Home dashboard (drag, resize, hide, compact and expanded layouts); browser and desktop notifications. Gate: spoken replies start in under 1.5 seconds on my PC, and voice can do everything chat can.
```

```markdown
PHASE 4, COMPUTER CONTROL, RESEARCH AND CODING (weeks 14-16)
Build the Operator agent with allow-listed apps and folders, an isolated Playwright profile, computer use for the screen, execution logs and a kill switch; the Research agent with web search, citations, and labels for verified facts, assumptions and opinions; the Coding agent with scoped GitHub access and Claude Code runs on my PC. Gate: 10 real tasks completed with no action outside policy.
```

```markdown
PHASE 5, WORK WORKSPACES, PERSONAL, FINANCE, FITNESS (weeks 17-19)
Build the security workspaces (vulnerability management with Inspector, GHAS, DAST and Guardium items, SLA and aging, escalations; AppSec, cloud and pentest boards; an OSCP learning track); personal goals, routines, lists, journal and important dates; finance (manual, voice and CSV entry, budgets, EMIs, debts, savings goals, cash flow; local model only; no payments); fitness (workouts with sets, reps and weight, exercise library, body metrics, nutrition, water, sleep, habits, weekly report; not medical advice). Gate: one full month of spending and workouts tracked.
```

```markdown
PHASE 6, AUTOMATION, ANALYTICS, PROACTIVE INTELLIGENCE (weeks 20-22)
Build the automation engine (natural-language workflow creation, schedule and event triggers, conditions, approval checkpoints, retries, run history, failure alerts) and the visual workflow builder; analytics (task completion, time allocation, habits, goals, workload, finance and fitness trends; only from real data); midday check-in, evening review, weekly and monthly reports; detection of overdue work, unanswered email, conflicts, overloaded days and repeatedly postponed tasks. Gate: 5 of my real routines run for two weeks without failing.
```

```markdown
PHASE 7, HARDENING AND RELEASE (weeks 23-24)
Run a security review of every sensitive and irreversible tool and a prompt-injection test suite; add agent evals; performance tuning; monitoring and alerts; backup and restore drill; Windows installer and auto-update; deployment guide, API docs, .env.example and setup guide. Gate: one month of daily use with no manual fixes.
```
