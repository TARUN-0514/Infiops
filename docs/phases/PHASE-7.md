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
