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

- [ ] Models and migration 0008: automation_workflows, automation_steps, automation_runs; approval_requests.automation_run_id
- [ ] Engine: next run time, event matching, step runner with templates, conditions, approvals, retries, failure alerts
- [ ] Worker: `automation_tick` every minute
- [ ] API: workflows CRUD, run now, runs with step log, decide a checkpoint, draft from text, tool catalogue
- [ ] Tool approvals inside a run resume the run
- [ ] Web: Automations page (list with 14-day health, builder, run history)
- [ ] Tests
