# Phase 6: automation, analytics and proactive intelligence

Phase 6 ships in two pull requests. Part 1 is the automation engine and builder. Part 2 is analytics, the midday check-in, evening review, weekly and monthly reports, and detection of overdue work, unanswered email, conflicts, overloaded days and repeatedly postponed tasks.

## Gate: 5 of Tarun's real routines run for two weeks without failing

Automations shows each workflow's runs over the last 14 days and its success rate, so the gate can be read straight off the page. It needs two weeks of real use, so it stays open until then.

## Part 1 decisions

- **Plain engine, no LangGraph yet.** A workflow is a trigger plus an ordered list of steps. Runs are saved after every step, so a run can wait for approval or a retry and pick up where it left off. The blueprint allows LangGraph for this engine; a plain step runner covers every step kind below, so I left it out and will only add it if branching flows need it.
- **Triggers:** manual; schedule (daily or chosen weekdays at a time, monthly on a day, or every N hours) in the owner's time zone; events from inside NEXUS (task created or completed, important email, finding past SLA, budget over, date coming up) with optional filters.
- **Step kinds:** tool (any registered tool, through the same permission check as chat: allowed tools run, sensitive and irreversible ones raise an approval card, forbidden ones never run), agent (the local model writes text from earlier results, which it sees as data), condition (stop unless true), approval checkpoint (pause until the owner says go), notify.
- **Retries** with backoff (1, 5, 15 minutes) up to each step's limit; then the run fails and the owner gets a failure alert.
- **Plain-language creation:** the local model turns a sentence into a draft workflow, which is validated and shown in the builder. Nothing is saved or run until the owner saves it.
- **Schedules without a new dependency:** the next run time is worked out in code rather than with a cron library.

## Part 1 tasks

- [x] Models and migration 0008: automation_workflows, automation_steps, automation_runs; approval_requests.automation_run_id
- [x] Engine: next run time, event matching, step runner with templates, conditions, approvals, retries, failure alerts
- [x] Worker: `automation_tick` every minute
- [x] API: workflows CRUD, run now, runs with step log, decide a checkpoint, draft from text, tool catalogue
- [x] Tool approvals inside a run resume the run
- [x] Web: Automations page (list with 14-day health, builder, run history)
- [x] Tests: 162 API (13 new), 75 web unit tests (6 new); browser run of the builder, drafting, run now, checkpoints, editing and phone width

## Part 1 notes

- **Menu:** Automations is marked as shipped ahead of the rest of phase 6, so it loses its "P6" badge; Analytics keeps it until part 2.
- **Event runs start on the worker's next minute tick**, not inside the request that raised the event, so a slow automation never slows the page you're on.
- **Not built yet:** external API steps and shared templates (later in the blueprint), drag-and-drop reordering (steps move with up and down buttons), and branching (a condition only stops the run).

## Part 2 decisions

- **Real data only.** Every number on Analytics is computed from stored rows. A rate with nothing to divide by is shown as "–", never 0%. Each section has its own empty state that says where its data comes from.
- **Detection is rules, not guesses.** Overdue: open tasks past their due date (all-day tasks after the day ends). Unanswered: email marked as needing a reply and not answered for 48 hours. Conflicts: overlapping events in the next 7 days, ignoring declined ones. Overloaded day: 6+ hours of meetings, 8+ tasks due, or 3+ tasks due with under an hour free between 9 and 6. Postponed: open tasks pushed back 3+ times. The thresholds are returned with the results.
- **Goals "behind"** compares progress with a straight line from the day the goal was set to its target date, and only flags a gap of more than 15 points.
- **Check-ins are always local.** The midday check-in and evening review are written by the local model with a plain fallback. The monthly report includes money and health totals, so it is marked secret and the gateway can never send it to the cloud.
- **The weekly report already existed** (Work, phase 2); part 2 adds the monthly one.

## Part 2 tasks

- [x] Detection service and `GET /insights`; "Needs attention" on Analytics and on Home
- [x] Analytics service and `GET /analytics?days=7|30|90`: tasks created vs completed, completion and on-time rates, overdue, most postponed, completed by project; time from work log minutes, meetings, study and workouts; habits with rates and streaks; goals against target; 14-day workload; cash flow and top spending; workouts, weight and sleep
- [x] Migration 0009: briefing kinds gain midday, evening and monthly
- [x] Midday check-in, evening review and monthly report: settings, scheduled delivery in `briefing_tick` with a notification, `GET /checkins/today`, `POST /checkins/{kind}`, `GET/POST /reports/monthly`
- [x] Chat tools: `insights_list` (read) and `analytics_summary` (read, local only)
- [x] Web: Analytics page; Briefing page tabs for morning, midday, evening and monthly, with one schedule card
- [x] Menu: phase 6 complete, so no module shows a "coming" page
- [x] Tests: 173 API (11 new), 81 web unit tests (6 new); browser run of empty and filled Analytics, 90-day range, Home card, check-ins, schedule toggle, monthly report and phone width

## Part 2 notes

- **Insight links open the page** (Tasks, Emails, Calendar), not the single item, because those pages don't take an item in the URL yet.
- **Monthly report runs on the 1st to 3rd** of the month, after the morning briefing time, for the month before. You can write one for any past month by hand.
- **Not built:** custom date ranges (7, 30 and 90 days only) and exporting analytics.

## End of phase 6

Full suite: 173 API tests, 81 web unit tests, mypy strict, ruff, TypeScript strict and ESLint all pass; migrations upgrade, downgrade and upgrade cleanly. The gate (five real routines running two weeks without failing) needs two weeks of real use and stays open until then.
