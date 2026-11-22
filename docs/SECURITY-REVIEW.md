# Security review: sensitive and irreversible tools

Phase 7 review of every tool the assistant can call that changes something outside a
plain database row, plus the prompt-injection paths into the model. Reviewed 22 Nov 2026
against the code on branch `phase-7a-security`. The risk table is pinned by
`tests/test_security_review.py`, so changing a tool's risk fails CI until this document
and that test are updated together.

## How every call is checked

1. The model can only name a tool from the registry. Unknown names fail.
2. Input is validated against the tool's schema with `extra="forbid"`, before any approval
   card is made. A model can't add fields such as `approved: true`.
3. The server decides: read, draft and reversible run; sensitive and irreversible create
   an `approval_requests` row and the run pauses; forbidden never runs. The owner may set
   a sensitive tool to "allow" (blueprint: "unless a routine allows it"); irreversible can
   never be set to allow, and forbidden can't be changed at all.
4. Only the owner's authenticated request to `POST /approvals/{id}/decide` runs a paused
   call. No tool can approve, change permissions or read tokens.
5. Every run, denial and approval request of a sensitive, irreversible or forbidden tool is
   written to `audit_logs`, on all three paths (chat, approval card, automation). Tool input
   is not copied into the audit row; it stays in `tool_executions`.

## Tools

| Tool | Risk | What can go wrong | Protection |
|---|---|---|---|
| `email_send` | irreversible | Mail to the wrong person, or content changed after approval | Approval card names subject and every recipient. The draft is locked while the request waits and unlocks if it expires or is rejected. Sends only an existing draft, never free text. |
| `tasks_delete` | sensitive | Losing a task and its subtasks | Card names the task and how many subtasks go with it. |
| `memory_forget` | sensitive | Losing a memory and its history | Card quotes the memory. |
| `calendar_create_event`, `calendar_update_event`, `calendar_time_block` | sensitive | Changing the owner's (and attendees') calendar | Card names the event, time and change. |
| `calendar_delete_event` | sensitive | Deleting a meeting | Card names the event and its time. |
| `files_write`, `files_move` | sensitive | Overwriting or moving files | Paths must be absolute, inside an allowed folder marked writable, with no `..`; the local agent resolves links again before acting. Overwrite is opt-in. |
| `browser_act` | sensitive | Submitting forms on sites | http/https only; runs in the isolated Playwright profile, not the owner's browser; each run audited. |
| `claude_code_run` | sensitive | Editing code | Folder must be allowed; edits only with `allow_edits` and a writable folder. |
| `computer_use` | sensitive | Acting on the owner's screen | Off unless screen control is enabled for a device and cloud is on; each run audited with its task. |
| `desktop_open_app`, `desktop_open_url` | reversible | Opening an app or link | Apps from an allow list only; URLs http/https only. Opening a link can't submit anything by itself, so it doesn't ask. |
| Finance, fitness, journal tools | reversible, local only | Money and health data reaching the cloud | Hidden from cloud runs; the monthly report is marked secret so the gateway never routes it to the cloud. |

There are no forbidden tools registered, and none that can pay, transfer, or touch sign-in
and security settings. A test fails if a tool name suggests otherwise.

## Prompt injection

Emails, web pages, files, documents, attachments, tool output and anything else NEXUS
reads are wrapped in a tag (`<email>`, `<web_page>`, `<file>`, `<passage>`, `<data>`,
`<facts>` and so on) and the system prompt says text inside is data. Every wrapper now
passes its content through `app/ai/untrusted.neutral`, which defuses any of those tag
names inside the text, so data can't close its block and start "instructions". Attribute
values (file names, document titles) are HTML-escaped. A static test fails if a new
wrapper forgets this.

The injection suite (`tests/test_prompt_injection.py`) also scripts a model that obeys an
injected email and shows the server still stops it: the send and the delete both wait for
the owner, and nothing leaves the machine. Email is never mined for memories.

## Findings fixed in this review

1. **Chat approvals and owner-allowed sensitive runs left no audit row.** Only the
   approval card and automation paths audited, and only operator tools audited their runs.
   Now every path audits requests, runs and denials.
2. **Approval cards were vague** ("Send an email", "Delete an event"), so the owner
   couldn't see the recipient or which item. Tools can now describe the call from stored
   data; the destructive ones do.
3. **A draft could change after its send was requested from chat**, so the owner could
   approve one text and send another. The draft is now locked for every path, and an
   expired request no longer leaves it locked forever (this also affected the Send button).
4. **Wrapped data could close its own tag** (an email body containing `</email>`). Fixed
   with `neutral()` on every wrapper, plus escaped attributes.
5. **Invalid tool input still produced an approval card** that would fail when approved.
   Input is now validated first and the call fails without asking.

## Left as is, on purpose

- `desktop_open_url` stays reversible: opening a page is visible and can't submit anything
  by itself. Revisit if the owner wants a confirmation.
- Sensitive tools can be set to "allow" by the owner, as the blueprint allows for routines.
  The Settings page shows the effective decision for each tool.
