# NEXUS API

The web app, the Windows app, the phone and the local agent all use this API. The full
machine-readable contract is [`api/openapi.json`](api/openapi.json); while developing, the
interactive version is at http://localhost:8000/api/v1/docs (turned off in production).
This page and `openapi.json` are generated from the code by
`services/api/scripts/export_openapi.py`, and CI fails if they are out of date.

## Signing in

1. `POST /api/v1/auth/login` with `{"email", "password"}` (and `"totp_code"` when
   two-factor is on) returns `{"access_token", "expires_in"}` and sets two cookies: an
   httpOnly refresh token and `nexus_csrf`.
2. Send `Authorization: Bearer <access_token>` on every call. Access tokens last 15 minutes.
3. `POST /api/v1/auth/refresh` with the header `X-CSRF-Token: <nexus_csrf cookie>` returns a
   new access token and rotates the refresh token. Reusing an old refresh token signs out
   that session.

The first account registered becomes the owner; registration then closes. Sign-in is
rate limited per address.

## Errors

Every error has the same shape and a status code that means what it says:

```json
{"error": {"code": "validation_error", "message": "Check the highlighted fields.",
           "fields": [{"field": "title", "message": "Field required"}]}}
```

`400` the request can't be done as asked (for example a draft locked while its send waits
for approval), `401` signed out or token expired, `403` not allowed, `404` not yours or not
there, `413` upload too large, `422` invalid input, `429` too many sign-in attempts.

## Actions that need approval

Tools the assistant runs are checked on the server against their risk level. A sensitive
or irreversible action (sending an email, deleting a task or an event, writing files)
creates an approval request instead of running: list them with `GET /api/v1/approvals`
and decide with `POST /api/v1/approvals/{id}/decide` `{"approve": true}`. Nothing a model
says can approve one. See [SECURITY-REVIEW.md](SECURITY-REVIEW.md).

## Chat streaming

`POST /api/v1/chat/conversations/{id}/messages` streams newline-delimited JSON events
(`run.started`, `memory.used`, `text.delta`, `tool.started`, `tool.finished`,
`approval.required`, `message.completed`, `run.finished`).
The run continues and is saved even if the client disconnects.

## Endpoints

241 endpoints in 21 groups. 🔒 means a signed-in owner only.


### Analytics

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/analytics` 🔒 | Overview |
| GET | `/api/v1/checkins/today` 🔒 | Checkins Today |
| POST | `/api/v1/checkins/{kind}` 🔒 | Write Checkin |
| GET | `/api/v1/insights` 🔒 | List Insights |
| GET | `/api/v1/reports/monthly` 🔒 | Monthly List |
| POST | `/api/v1/reports/monthly` 🔒 | Monthly Write |

### Assistant

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/ai/status` 🔒 | Ai Status |
| GET | `/api/v1/ai/usage` 🔒 | Ai Usage |
| GET | `/api/v1/approvals` 🔒 | List Approvals |
| POST | `/api/v1/approvals/{approval_id}/decide` 🔒 | Decide Approval |
| GET | `/api/v1/chat/conversations` 🔒 | List Conversations |
| POST | `/api/v1/chat/conversations` 🔒 | Create Conversation |
| GET | `/api/v1/chat/conversations/{cid}` 🔒 | Get Conversation |
| PATCH | `/api/v1/chat/conversations/{cid}` 🔒 | Rename Conversation |
| DELETE | `/api/v1/chat/conversations/{cid}` 🔒 | Delete Conversation |
| POST | `/api/v1/chat/conversations/{cid}/messages` 🔒 | Runs one turn and streams events as NDJSON. The run continues even if the client |
| GET | `/api/v1/chat/search` 🔒 | Search Messages |
| GET | `/api/v1/tools` 🔒 | List Tools |
| PUT | `/api/v1/tools/{name}/permission` 🔒 | Set Permission |
| POST | `/api/v1/uploads` 🔒 | Upload |

### Auth

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/logout` 🔒 | Logout |
| GET | `/api/v1/auth/me` 🔒 | Me |
| POST | `/api/v1/auth/mfa/disable` 🔒 | Mfa Disable |
| POST | `/api/v1/auth/mfa/enable` 🔒 | Mfa Enable |
| POST | `/api/v1/auth/mfa/setup` 🔒 | Mfa Setup |
| POST | `/api/v1/auth/refresh` | Refresh |
| POST | `/api/v1/auth/register` | Register |
| GET | `/api/v1/auth/sessions` 🔒 | List Sessions |
| DELETE | `/api/v1/auth/sessions/{session_id}` 🔒 | Revoke Session |
| GET | `/api/v1/auth/status` | Auth Status |

### Automations

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/automation-runs` 🔒 | List Runs |
| GET | `/api/v1/automation-runs/{rid}` 🔒 | Get Run |
| POST | `/api/v1/automation-runs/{rid}/cancel` 🔒 | Cancel Run |
| POST | `/api/v1/automation-runs/{rid}/decide` 🔒 | Decide Checkpoint |
| GET | `/api/v1/automations` 🔒 | List Workflows |
| POST | `/api/v1/automations` 🔒 | Create Workflow |
| POST | `/api/v1/automations/draft` 🔒 | Draft Workflow |
| GET | `/api/v1/automations/meta` 🔒 | Meta |
| GET | `/api/v1/automations/{wid}` 🔒 | Get Workflow |
| PUT | `/api/v1/automations/{wid}` 🔒 | Update Workflow |
| PATCH | `/api/v1/automations/{wid}` 🔒 | Set Enabled |
| DELETE | `/api/v1/automations/{wid}` 🔒 | Delete Workflow |
| POST | `/api/v1/automations/{wid}/run` 🔒 | Run Now |

### Briefing

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/briefings` 🔒 | History |
| PUT | `/api/v1/briefings/settings` 🔒 | Save Settings |
| GET | `/api/v1/briefings/today` 🔒 | Today |
| POST | `/api/v1/briefings/today` 🔒 | Generate Today |
| POST | `/api/v1/briefings/{bid}/read` 🔒 | Mark Read |
| GET | `/api/v1/notifications` 🔒 | List Notifications |
| POST | `/api/v1/notifications/read-all` 🔒 | Read All |
| POST | `/api/v1/notifications/{nid}/read` 🔒 | Read One |
| GET | `/api/v1/push/key` 🔒 | Push Key |
| POST | `/api/v1/push/subscriptions` 🔒 | Subscribe |
| POST | `/api/v1/push/test` 🔒 | Push Test |
| POST | `/api/v1/push/unsubscribe` 🔒 | Unsubscribe |
| GET | `/api/v1/reports` 🔒 | List Reports |
| POST | `/api/v1/reports` 🔒 | Make Report |
| GET | `/api/v1/worklog` 🔒 | List Worklog |
| POST | `/api/v1/worklog` 🔒 | Add Log |
| PATCH | `/api/v1/worklog/{lid}` 🔒 | Update Log |
| DELETE | `/api/v1/worklog/{lid}` 🔒 | Delete Log |

### Calendar

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/calendar/events` 🔒 | List Events |
| POST | `/api/v1/calendar/events` 🔒 | Create Event |
| PATCH | `/api/v1/calendar/events/{eid}` 🔒 | Update Event |
| DELETE | `/api/v1/calendar/events/{eid}` 🔒 | Delete Event |
| GET | `/api/v1/calendar/free-slots` 🔒 | Free Slots |
| POST | `/api/v1/calendar/time-block` 🔒 | Time Block |

### Devices

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/devices` 🔒 | List Devices |
| POST | `/api/v1/devices/pair` | Called by the local agent with a code the owner made in Settings > Devices. |
| POST | `/api/v1/devices/pair-code` 🔒 | Pair Code |
| POST | `/api/v1/devices/token` | Device Token |
| PATCH | `/api/v1/devices/{device_id}` 🔒 | Update Device |
| DELETE | `/api/v1/devices/{device_id}` 🔒 | Remove Device |
| POST | `/api/v1/devices/{device_id}/stop` 🔒 | Kill switch: the agent stops listening at once and hands-free is turned off. |

### Email

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/email/drafts` 🔒 | List Drafts |
| POST | `/api/v1/email/drafts` 🔒 | Create Draft |
| PATCH | `/api/v1/email/drafts/{did}` 🔒 | Update Draft |
| DELETE | `/api/v1/email/drafts/{did}` 🔒 | Discard Draft |
| POST | `/api/v1/email/drafts/{did}/save-to-gmail` 🔒 | Save To Gmail |
| POST | `/api/v1/email/drafts/{did}/send` 🔒 | Asks for approval. Nothing is sent until the owner approves the request. |
| GET | `/api/v1/email/messages` 🔒 | List Messages |
| GET | `/api/v1/email/messages/{mid}` 🔒 | Get Message |
| PATCH | `/api/v1/email/messages/{mid}` 🔒 | The owner corrects the model's triage. |
| POST | `/api/v1/email/messages/{mid}/draft` 🔒 | Ai Draft |
| POST | `/api/v1/email/messages/{mid}/follow-up` 🔒 | Follow Up |
| GET | `/api/v1/email/summary` 🔒 | Summary |
| POST | `/api/v1/email/sync` 🔒 | Sync |
| POST | `/api/v1/email/triage` 🔒 | Triage |

### Finance

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/finance/accounts` 🔒 | List Accounts |
| POST | `/api/v1/finance/accounts` 🔒 | Create Account |
| PATCH | `/api/v1/finance/accounts/{account_id}` 🔒 | Update Account |
| DELETE | `/api/v1/finance/accounts/{account_id}` 🔒 | Delete Account |
| GET | `/api/v1/finance/budgets` 🔒 | List Budgets |
| PUT | `/api/v1/finance/budgets` 🔒 | Put Budgets |
| GET | `/api/v1/finance/cashflow` 🔒 | Cashflow |
| GET | `/api/v1/finance/debts` 🔒 | List Debts |
| POST | `/api/v1/finance/debts` 🔒 | Create Debt |
| GET | `/api/v1/finance/debts/plan` 🔒 | Debt Plan |
| PATCH | `/api/v1/finance/debts/{did}` 🔒 | Update Debt |
| DELETE | `/api/v1/finance/debts/{did}` 🔒 | Delete Debt |
| GET | `/api/v1/finance/goals` 🔒 | List Goals |
| POST | `/api/v1/finance/goals` 🔒 | Create Goal |
| PATCH | `/api/v1/finance/goals/{gid}` 🔒 | Update Goal |
| DELETE | `/api/v1/finance/goals/{gid}` 🔒 | Delete Goal |
| POST | `/api/v1/finance/import` 🔒 | Import Csv |
| POST | `/api/v1/finance/import/preview` 🔒 | Import Preview |
| GET | `/api/v1/finance/meta` 🔒 | Meta |
| GET | `/api/v1/finance/recurring` 🔒 | List Recurring |
| POST | `/api/v1/finance/recurring` 🔒 | Create Recurring |
| PATCH | `/api/v1/finance/recurring/{rid}` 🔒 | Update Recurring |
| DELETE | `/api/v1/finance/recurring/{rid}` 🔒 | Delete Recurring |
| POST | `/api/v1/finance/recurring/{rid}/paid` 🔒 | Mark Paid |
| GET | `/api/v1/finance/summary` 🔒 | Summary |
| GET | `/api/v1/finance/transactions` 🔒 | List Transactions |
| POST | `/api/v1/finance/transactions` 🔒 | Create Transaction |
| POST | `/api/v1/finance/transactions/quick` 🔒 | '450 swiggy dinner' or 'salary 85000': parsed on the server, no model needed. |
| PATCH | `/api/v1/finance/transactions/{tx_id}` 🔒 | Update Transaction |
| DELETE | `/api/v1/finance/transactions/{tx_id}` 🔒 | Delete Transaction |

### Fitness

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/fitness/bests` 🔒 | Personal Bests |
| GET | `/api/v1/fitness/exercises` 🔒 | Exercises |
| POST | `/api/v1/fitness/exercises` 🔒 | Add Exercise |
| DELETE | `/api/v1/fitness/exercises/{eid}` 🔒 | Delete Exercise |
| GET | `/api/v1/fitness/logs` 🔒 | List Logs |
| POST | `/api/v1/fitness/logs` 🔒 | Add Log |
| DELETE | `/api/v1/fitness/logs/{lid}` 🔒 | Delete Log |
| GET | `/api/v1/fitness/metrics` 🔒 | Metric Specs |
| GET | `/api/v1/fitness/report` 🔒 | Weekly Report |
| GET | `/api/v1/fitness/workouts` 🔒 | List Workouts |
| POST | `/api/v1/fitness/workouts` 🔒 | Create Workout |
| PUT | `/api/v1/fitness/workouts/{sid}` 🔒 | Update Workout |
| DELETE | `/api/v1/fitness/workouts/{sid}` 🔒 | Delete Workout |
| GET | `/api/v1/habits` 🔒 | List Habits |
| POST | `/api/v1/habits` 🔒 | Create Habit |
| PATCH | `/api/v1/habits/{hid}` 🔒 | Update Habit |
| DELETE | `/api/v1/habits/{hid}` 🔒 | Delete Habit |
| PUT | `/api/v1/habits/{hid}/days` 🔒 | Tick Habit |
| GET | `/api/v1/tracking/month` 🔒 | Which days of a month have spending and workouts logged. |

### Health

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/healthz` | Liveness: the process is up. |
| GET | `/readyz` | Readiness: dependencies answer. |

### Integrations

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/integrations` 🔒 | List Integrations |
| POST | `/api/v1/integrations/google/start` 🔒 | Google Start |
| DELETE | `/api/v1/integrations/{account_id}` 🔒 | Disconnect |
| POST | `/api/v1/integrations/{account_id}/sync` 🔒 | Sync Now |
| POST | `/api/v1/integrations/{account_id}/test` 🔒 | Test |

### Knowledge

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/v1/knowledge/ask` 🔒 | Ask |
| GET | `/api/v1/knowledge/documents` 🔒 | List Documents |
| POST | `/api/v1/knowledge/documents` 🔒 | Upload |
| GET | `/api/v1/knowledge/documents/{did}` 🔒 | Get Document |
| PATCH | `/api/v1/knowledge/documents/{did}` 🔒 | Update Document |
| DELETE | `/api/v1/knowledge/documents/{did}` 🔒 | Delete Document |
| POST | `/api/v1/knowledge/documents/{did}/reprocess` 🔒 | Reprocess |
| GET | `/api/v1/knowledge/search` 🔒 | Search |

### Memory

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/memory` 🔒 | List Memories |
| POST | `/api/v1/memory` 🔒 | Add Memory |
| GET | `/api/v1/memory/categories` | Categories |
| GET | `/api/v1/memory/conflicts` 🔒 | Conflicts |
| POST | `/api/v1/memory/conflicts/{conflict_id}/resolve` 🔒 | Resolve |
| GET | `/api/v1/memory/consent` 🔒 | Get Consent |
| PUT | `/api/v1/memory/consent` 🔒 | Put Consent |
| GET | `/api/v1/memory/{memory_id}` 🔒 | Get Memory |
| PATCH | `/api/v1/memory/{memory_id}` 🔒 | Edits never overwrite: a new version supersedes the old one. |
| DELETE | `/api/v1/memory/{memory_id}` 🔒 | Forget Memory |
| POST | `/api/v1/memory/{memory_id}/confirm` 🔒 | Confirm Memory |
| GET | `/api/v1/memory/{memory_id}/history` 🔒 | Memory History |

### Operator

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/integrations/github` 🔒 | Github Status |
| POST | `/api/v1/integrations/github/test` 🔒 | Real call to GitHub. Connected only if it answers. |
| GET | `/api/v1/operator/activity` 🔒 | Activity |
| GET | `/api/v1/operator/policy` 🔒 | Get Policy |
| PUT | `/api/v1/operator/policy` 🔒 | Put Policy |
| POST | `/api/v1/operator/resume` 🔒 | Resume |
| POST | `/api/v1/operator/stop` 🔒 | Stop |
| GET | `/api/v1/research` 🔒 | List Research |
| POST | `/api/v1/research` 🔒 | Start Research |
| GET | `/api/v1/research/{report_id}` 🔒 | Get Research |
| DELETE | `/api/v1/research/{report_id}` 🔒 | Delete Research |

### Personal

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/goals` 🔒 | List Goals |
| POST | `/api/v1/goals` 🔒 | Create Goal |
| PUT | `/api/v1/goals/{gid}` 🔒 | Update Goal |
| DELETE | `/api/v1/goals/{gid}` 🔒 | Delete Goal |
| GET | `/api/v1/important-dates` 🔒 | List Dates |
| POST | `/api/v1/important-dates` 🔒 | Create Date |
| PUT | `/api/v1/important-dates/{did}` 🔒 | Update Date |
| DELETE | `/api/v1/important-dates/{did}` 🔒 | Delete Date |
| GET | `/api/v1/journal` 🔒 | List Journal |
| POST | `/api/v1/journal` 🔒 | Add Entry |
| PUT | `/api/v1/journal/{eid}` 🔒 | Update Entry |
| DELETE | `/api/v1/journal/{eid}` 🔒 | Delete Entry |
| PATCH | `/api/v1/list-items/{iid}` 🔒 | Update Item |
| DELETE | `/api/v1/list-items/{iid}` 🔒 | Delete Item |
| GET | `/api/v1/lists` 🔒 | List Lists |
| POST | `/api/v1/lists` 🔒 | Create List |
| PUT | `/api/v1/lists/{lid}` 🔒 | Update List |
| DELETE | `/api/v1/lists/{lid}` 🔒 | Delete List |
| POST | `/api/v1/lists/{lid}/items` 🔒 | Add Item |
| GET | `/api/v1/routines` 🔒 | List Routines |
| POST | `/api/v1/routines` 🔒 | Create Routine |
| PUT | `/api/v1/routines/{rid}` 🔒 | Update Routine |
| DELETE | `/api/v1/routines/{rid}` 🔒 | Delete Routine |
| PUT | `/api/v1/routines/{rid}/log` 🔒 | Log Routine |

### Preferences

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/preferences/home` 🔒 | Get Home |
| PUT | `/api/v1/preferences/home` 🔒 | Put Home |

### Status

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/status` 🔒 | System Status |

### Tasks

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/projects` 🔒 | List Projects |
| POST | `/api/v1/projects` 🔒 | Create Project |
| PATCH | `/api/v1/projects/{project_id}` 🔒 | Update Project |
| GET | `/api/v1/tasks` 🔒 | List Tasks |
| POST | `/api/v1/tasks` 🔒 | Create Task |
| POST | `/api/v1/tasks/parse` 🔒 | Preview a task from a sentence. Nothing is saved until the owner confirms. |
| GET | `/api/v1/tasks/today` 🔒 | Today |
| GET | `/api/v1/tasks/{task_id}` 🔒 | Get Task |
| PATCH | `/api/v1/tasks/{task_id}` 🔒 | Update Task |
| DELETE | `/api/v1/tasks/{task_id}` 🔒 | Delete Task |
| POST | `/api/v1/tasks/{task_id}/complete` 🔒 | Complete |
| POST | `/api/v1/tasks/{task_id}/postpone` 🔒 | Postpone |

### Voice

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/v1/voice/speak` 🔒 | Speak |
| GET | `/api/v1/voice/status` 🔒 | Voice Status |
| POST | `/api/v1/voice/transcribe` 🔒 | Transcribe |

### Workspaces

| Method | Path | What it does |
| --- | --- | --- |
| DELETE | `/api/v1/learning/sessions/{sid}` 🔒 | Delete Session |
| PATCH | `/api/v1/learning/topics/{tid}` 🔒 | Update Topic |
| DELETE | `/api/v1/learning/topics/{tid}` 🔒 | Delete Topic |
| POST | `/api/v1/learning/topics/{tid}/review` 🔒 | Review Topic |
| GET | `/api/v1/learning/tracks` 🔒 | List Tracks |
| POST | `/api/v1/learning/tracks` 🔒 | Create Track |
| GET | `/api/v1/learning/tracks/{tid}` 🔒 | Get Track |
| PATCH | `/api/v1/learning/tracks/{tid}` 🔒 | Update Track |
| DELETE | `/api/v1/learning/tracks/{tid}` 🔒 | Delete Track |
| POST | `/api/v1/learning/tracks/{tid}/sessions` 🔒 | Add Session |
| POST | `/api/v1/learning/tracks/{tid}/topics` 🔒 | Add Topic |
| GET | `/api/v1/workspace-items/{iid}` 🔒 | Get Item |
| PATCH | `/api/v1/workspace-items/{iid}` 🔒 | Update Item |
| DELETE | `/api/v1/workspace-items/{iid}` 🔒 | Delete Item |
| POST | `/api/v1/workspace-items/{iid}/escalate` 🔒 | Records an escalation. NEXUS doesn't email anyone; draft that from Emails if needed. |
| GET | `/api/v1/workspaces` 🔒 | List Workspaces |
| POST | `/api/v1/workspaces` 🔒 | Create Workspace |
| PUT | `/api/v1/workspaces/{wid}` 🔒 | Update Workspace |
| DELETE | `/api/v1/workspaces/{wid}` 🔒 | Delete Workspace |
| POST | `/api/v1/workspaces/{wid}/import` 🔒 | Import Findings |
| GET | `/api/v1/workspaces/{wid}/items` 🔒 | List Items |
| POST | `/api/v1/workspaces/{wid}/items` 🔒 | Create Item |
| GET | `/api/v1/workspaces/{wid}/summary` 🔒 | Workspace Summary |
