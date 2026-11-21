# Phase 1: AI core, memory, chat and tasks

## Design change: local-first (decided 2026-11-21)

Tarun chose to run NEXUS **local-first and at no cost by default**. Every model job (chat, tools, memory extraction, task parsing, embeddings) runs on his PC through an OpenAI-compatible server (Ollama or LM Studio, Vulkan/ROCm on the RX 9060 XT 16 GB). The default model is Qwen3 14B Q4, with bge-m3 for embeddings. Cloud (Claude) is an **optional, off-by-default switch** chosen per message for very hard tasks, with a daily token cap. Secret data never goes to the cloud.

## Tasks

- [x] Migration 0002: pgvector; conversations and messages (full-text search); agent runs (checkpointed state); tool executions; approval requests; permission policies; model usage logs; memory items, sources and conflicts; projects; tasks; uploads
- [x] Model gateway: local provider (streaming, tool calls, `<think>` filtering, structured output), Anthropic provider (streaming, tools, prompt caching, refusal fallback), job→model config, cloud switch with daily cap, usage logging, honest errors when a model is unreachable
- [x] Tool registry with risk levels; server-side permission engine (forbidden always denied, irreversible always asks); per-tool owner policies
- [x] Orchestrator: context with profile, local time, retrieved memories and open tasks wrapped as data; tool loop (max 8 steps); pauses for approval and resumes from the checkpoint; dangling approvals expire when the owner moves on
- [x] Chat API streamed as NDJSON, with history, search, rename, delete and uploads (images, PDF, text; type and magic-byte checks)
- [x] Memory engine: dedupe with merged sources, supersede (never overwrite), confirm, forget (all versions), hybrid full-text + vector search, consent per category, extraction job, conflict review
- [x] Tasks and projects: subtasks, RRULE recurrence (completion rolls forward), postpone count, today/overdue, natural-language parse preview
- [x] Web: Assistant (chat, memory browser, approvals centre), Tasks (list and kanban), Projects, Home (Ask NEXUS bar and Today), Settings (AI models, tool permissions, memory consent)
- [x] Tests: 49 API tests and 19 web unit tests; end-to-end browser run against a stand-in local model server
- [x] Windows quick start (Docker Desktop and native Ollama/LM Studio) in the README

## Gate

1. **NEXUS remembers facts across sessions, with sources.** Covered by tests: extraction stores facts with their source message, a later chat retrieves them and cites them (`memory.used`), and the memory browser shows where each fact came from. Check it by hand: tell NEXUS a preference in one chat, start a new chat and ask about it.
2. **Creates tasks correctly from 20 test sentences.** Run `uv run python scripts/eval_task_parsing.py` with the local model running. This needs a real model, so it is not part of CI. **Not yet run against a real model**, because the build environment can't download model weights.

## Deliberately left for later

- Voice, the WebSocket transport and the desktop agent: phase 3. Chat streams over HTTP (NDJSON) for now.
- S3/MinIO storage: uploads use a local Docker volume until documents arrive in phase 4.
- The local model can't read PDFs directly. It asks you to paste the text or use cloud; PDF text extraction arrives with the knowledge base.
- Weather on Home: needs an outside service, so it comes with the phase 2 integrations.
- Generating the TypeScript client from OpenAPI: types are still written by hand.
