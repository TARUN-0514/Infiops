# Phase 5: finance, fitness and habits (part 1)

Phase 5 ships in two pull requests. This one is finance, fitness and habits. The next one is the security workspaces (vulnerability management, AppSec, cloud and pentest boards, the OSCP track) and the personal pages (goals, routines, lists, journal, important dates).

## Decisions

- **Local model only for money and health.** Finance and fitness tools are marked `local_only`. A cloud run doesn't see them, is refused if it calls one, and gets no finance or health memories in its context. A conversation that already holds results from those tools stays on the local model even with Use cloud on, and the chat says so. Memory extraction now follows what the run actually used, which also fixes secret chats (they were sent to the cloud for extraction when Use cloud was on).
- **Encrypted at rest.** Money amounts, health values, descriptions and notes are AES-GCM encrypted columns (`EncryptedText`, `EncryptedDecimal`, keyed by `NEXUS_ENCRYPTION_KEY`, bound to their table and column). Sums are worked out in Python after decrypting, which is fine at one person's scale. Search in transactions filters after decrypting.
- **One table for health logs.** Body weight, body fat, waist, calories, protein, water and sleep share `health_logs` with a `metric` column, instead of the blueprint's separate body, nutrition, water and sleep tables. It's one shape (day, value, note), so one table keeps the API and the charts simple. Food, water and sleep add up over a day; body measures use the latest reading.
- **No model for entry.** Quick add and CSV import use rules (amount words like 2.5k, 1.2 lakh; keyword categories). The owner can change any category. CSV duplicates are detected with an HMAC of date, kind, amount and description, so the hash reveals nothing.
- **No payments.** Bills and EMIs remind and record; there's no tool that moves money.
- **Exercise library** is a built-in list of 32 common exercises in code, plus the owner's own in `exercises`.
- **Charts** use Recharts (named in the stack), pinned at 3.2.1.

## Tasks

- [x] Models and migration 0006: accounts, transactions, budgets, recurring payments, debts, savings goals, exercises, workout sessions and sets, health logs, habits and habit logs
- [x] Finance API: accounts with balances, transactions (manual, quick, CSV preview and import), monthly summary with budgets and upcoming bills, cash flow, budgets, EMIs and bills with mark paid, debts with avalanche and snowball payoff plans, savings goals
- [x] Fitness API: exercise library, workouts with sets, heaviest sets, health logs, habits with streaks, weekly report, month tracking calendar
- [x] Tools (local only): `finance_add_transaction`, `finance_summary`, `fitness_log_workout`, `fitness_log_metric`, `habit_tick`, `fitness_week`
- [x] Worker: hourly `reminders_tick` (bill reminders once per payment per cycle, after 8 AM local time; part 2 added SLA, follow-up and date reminders to the same job)
- [x] Web: Finance (Overview, Transactions, Import, Budgets, EMIs and bills, Debts, Goals) and Fitness (Workouts, Body and food, Habits, This week)
- [x] Tests: 132 API (26 new), 22 local agent, 58 web unit tests (10 new); browser run of every tab at desktop and phone width

## Gate: one full month of spending and workouts tracked

Fitness › This week › **Month tracked** counts the days in a month with spending and with workouts. The browser check tracked a sample month (manual entries, a CSV statement, chat, a workout, body logs, habits) and the calendar showed it correctly. **The gate itself needs a real month of Tarun's use**, so it stays open until then.

## Left for later

- Splitting one transaction across categories, and rules the owner can edit for auto-categories.
- PDF bank statements (CSV only for now).
- A plain-language weekly fitness summary from the local model (the report is numbers only for now).

# Phase 5 part 2: security workspaces and personal life

## Decisions

- **Workspaces are generic boards.** Each has its own statuses (some marked closed), optional custom fields (text, number, select, date) and optional SLA days by severity. Four start empty: Vulnerability management (SLA 7, 30, 90, 180 days for critical to low), AppSec, Cloud security and Pentests. The owner can make more.
- **SLA and aging are worked out on read** from found date, due date and closed date, so changing a board's SLA doesn't rewrite history. Dashboard: open, past SLA, due in 7 days, escalated, mean days to close, percent closed within SLA, severity split, age buckets.
- **Imports, no live connectors yet.** Upload a GHAS alerts JSON (`gh api repos/OWNER/REPO/code-scanning/alerts`, also Dependabot and secret scanning), an Inspector findings JSON export, or a CSV from a DAST scanner, Guardium or a pentest (columns found by name). Findings are keyed by alert URL or ARN, so re-importing closes what the scanner reports fixed and reopens what comes back. Live API sync with AWS and GitHub needs new credentials and scopes, so I left it for a later phase and will ask first.
- **Escalation records only.** Escalate notes who and why and sets a follow-up date; it never sends mail. The chat tool works the same way.
- **Finding text is untrusted.** Scanner descriptions are shown as text, never acted on, and the chat tool's output says so.
- **OSCP track.** A track can start from a PEN-200 syllabus (32 topics in 8 sections). Reviews use a simple spaced-repetition step (forgot resets to 1 day; good recall grows the gap up to 180 days). The lab log counts machines and roots.
- **Journal is encrypted** (`EncryptedText`) and its chat tool is local only. Search decrypts and filters in Python.
- **Important dates** repeat yearly or once; 29 February falls on 28 February in other years; a reminder goes out once per occurrence.
- **Navigation:** Personal is a new menu item between Fitness and Work. The blueprint lists Personal as a module but not in its 13 menu items; this is the one departure, and easy to move if you'd rather have it elsewhere.

## Tasks

- [x] Models and migration 0007: workspaces, items, item events, learning tracks, topics, sessions, goals, routines, routine logs, lists, list items, journal entries, important dates
- [x] Workspaces API: boards, items with filters, history, escalate, import with dry run, summary
- [x] Learning API: tracks (OSCP template), topics, reviews, sessions
- [x] Personal API: goals with milestones, routines with daily steps, lists, journal (month, search, tags), important dates
- [x] Tools: `workspace_find`, `workspace_add`, `workspace_update`, `learning_log`, `list_add`, `personal_overview`, and `journal_add` (local only)
- [x] Worker: `reminders_tick` adds SLA breach, follow-up and date reminders, each sent once
- [x] Web: Work gains Vulnerabilities, Boards and Learning tabs; new Personal page (Goals, Routines, Lists, Journal, Important dates)
- [x] Tests: 149 API (17 new), 69 web unit tests (11 new); browser run of every tab at desktop and phone width

## Left for later

- Live sync from AWS Inspector and GitHub (needs credentials and scopes; will ask).
- Drag and drop on boards (cards move with a next-status button or the status menu).
- Travel planning beyond a travel list.
