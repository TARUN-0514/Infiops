# Phase 4: computer control, research and coding

## Decisions

- **Local search, read-only GitHub** (the recommended option on the decision card; switch if Tarun picks another). Web search is a private SearXNG server in Docker: free, no API key, no paid service. GitHub uses a fine-grained, read-only token for a listed set of repositories. No new OAuth scope.
- **Two locks on computer control.** It is off until Tarun runs `nexus-agent control on` on the PC *and* turns it on in Settings. The server checks the policy before sending an action; the agent checks it again with the real file system (links followed, system and credential folders always refused). A device can only answer actions sent to it.
- **Risk levels.** Listing and reading files, reading web pages and GitHub are `read`. Opening an allowed app or link is `reversible`. Writing or moving a file, browser actions, Claude Code runs and screen control are `sensitive`, so each waits for approval. There is no delete tool.
- **Kill switch.** Stop everything pauses control on the server, tells every PC to cancel what is running (Claude Code processes are killed, the browser closes), and long runs re-read the policy before every step. Voice "Stop listening" does not pause computer control.
- **NEXUS's own browser** is Playwright Chromium with a separate profile, never Tarun's own browser. It refuses non-web schemes and password fields.
- **Screen control** is Claude's computer-use toolset (`computer_toolset_20260801`), so it needs cloud on and sends screenshots to Claude. The approval card says so. Screenshots are scaled to about 1280x800 and never stored, only a text log of actions. Some shortcuts (Ctrl+Alt+Del, Win+L) are refused.
- **Claude Code** runs on the PC with Tarun's own Claude Code sign-in, plan-only unless edits are allowed for that run. It never pushes or deploys.
- **Research findings are labelled** verified, assumption or opinion. "Verified" needs a page NEXUS actually read; the server downgrades any claim that doesn't cite one. Pages are wrapped as untrusted data, and private network addresses are refused on every redirect.

## Tasks

- [x] Operator policy API (`/operator/policy`, `/operator/stop`, `/operator/resume`, `/operator/activity`) with audit log rows
- [x] Call path to the PC over the device socket, with timeouts and per-device answers
- [x] Tools: `desktop_open_app`, `desktop_open_url`, `files_list`, `files_read`, `files_write`, `files_move`, `browser_read`, `browser_act`, `computer_use`, `claude_code_run`, `web_search`, `web_fetch`, `research_run`, `github_pulls`, `github_pull`, `github_issues`, `github_issue`
- [x] Research reports (`/research`, migration 0005, worker job)
- [x] GitHub read-only client with repository allow-list; status from a real test call
- [x] Local agent: `nexus-agent control on|off`, policy enforcement, files, apps, browser, screen, Claude Code, Stop
- [x] Web: Settings › Computer control, AI Assistant › Research and › Activity, GitHub card, kill switch on both pages
- [x] Docker `search` service (SearXNG with JSON output)
- [x] Tests: 106 API (20 new), 22 local agent (10 new), 48 web unit tests; browser run with a real agent process

## Gate: 10 real tasks with no action outside policy

Run in tests and the browser check (a real `nexus-agent` on a real folder, a stand-in model):

| # | Task | Result |
| - | --- | --- |
| 1 | List the allowed folder | Done on the PC |
| 2 | Read a file in it (contents wrapped as untrusted) | Done |
| 3 | Save a note | Waited for approval, written only after Approve |
| 4 | Read `/etc/shadow` / the SAM file | Refused on the server; nothing sent to the PC |
| 5 | Open an app that isn't allowed | Refused |
| 6 | Read through a link that leads outside the folder | Refused on the PC |
| 7 | Act after Stop everything | Refused while paused; allowed after Resume |
| 8 | Screen control run, stopped mid-run | Stopped before the next click |
| 9 | Research a question | Report with labelled findings; unsupported "verified" claims downgraded |
| 10 | Read a PR diff in an allowed repo, then a repo not on the list | First done, second refused |

**Needs checking on Tarun's PC:** the same ten with the real model (Qwen3 14B), real web search, Playwright Chromium, Claude Code and a cloud key for screen control. None could be run in the build environment (no internet, no Windows desktop).

## Left for later

- GitHub comments and PR creation (would need a write token and approval cards).
- Reading PDF and Word files on the PC (text files only for now; uploads to the Knowledge Base cover documents).
- A per-site allow-list for NEXUS's browser.
