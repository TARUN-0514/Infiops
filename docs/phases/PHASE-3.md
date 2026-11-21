# Phase 3: voice and desktop

## Decisions

- **Voice is local, like the AI.** Speech recognition is Whisper and the voice is Piper, both on Tarun's PC. Nothing he says goes to the cloud. The blueprint also lists OpenAI Realtime; it isn't used, because local-first was chosen in Phase 1.
- **One small voice server** (`services/voice`, Docker service `voice`) runs faster-whisper and Piper behind an OpenAI-style HTTP API. It runs on the CPU in Docker, which is fast enough for short commands on a Ryzen 7 9700X. For a faster or larger model, NEXUS can point at whisper.cpp's own server built for Vulkan, which uses the Radeon GPU (README › Voice). The API accepts either, through `NEXUS_STT_URL`.
- **Speech-to-text default is `base.en`** for speed. `small.en` is more accurate and still quick. Set `NEXUS_VOICE_STT_MODEL`.
- **The wake word is "Hey Jarvis".** openWakeWord has no pretrained "Hey NEXUS" model, and training one needs a separate training run. The agent accepts a custom `.onnx` model (`--wake-word path/to/hey_nexus.onnx`), so a "Hey NEXUS" model can drop in later.
- **Spoken turns use the same assistant and tools as chat.** The only differences are a short plain-speech reply style, Qwen3's thinking turned off (`/no_think`) for speed, and never routing to the slower planning model. Approvals still happen on screen; the voice says that something is waiting.
- **The local agent has its own session.** Pairing uses a one-time code from Settings and gives the PC its own rotating refresh token. That token is stored in `%APPDATA%\NEXUS\agent.json`, readable only by Tarun's Windows account. Removing the PC in Settings ends its session and disconnects it at once.
- **Desktop app** is a thin Tauri 2 shell around the web app (no second UI), with a tray icon, a global Ctrl+Shift+Space push-to-talk, Windows notifications and the agent started with the app. The web page inside it may only listen for the shortcut and show notifications.
- **The browser's own voice is a fallback only** when the voice server is down, and it is labelled as such. Speech recognition never falls back to the browser, because Chrome and Edge send audio to Google and Microsoft.

## Tasks

- [x] Voice server: `/v1/audio/transcriptions` (also `/inference`, the whisper.cpp path) and `/v1/audio/speech`; models download on first use
- [x] API: `/voice/transcribe`, `/voice/speak`, `/voice/status` (real test calls, "working" only when each answered); spoken chat turns
- [x] Device pairing: one-time codes, per-device session with rotation and reuse detection, WebSocket with presence and mic state, settings pushed live, **Stop listening** kill switch, removal
- [x] Local agent (`services/local-agent`): `nexus-agent pair | run | status | unpair`; wake word (openWakeWord), end-of-speech detection, hands-free follow-ups, replies spoken sentence by sentence as they stream, talk over NEXUS to interrupt, first-audio latency logged
- [x] Web: push-to-talk on every page (mic button or Ctrl+Shift+Space), interruption, turn latency shown, mic indicator for the browser and paired PCs, Settings › Voice and devices
- [x] Windows app (`apps/desktop`): Tauri 2 window, tray (open, push to talk, start/stop agent, quit), close to tray, single instance, offline page
- [x] Customisable Home: reorder by drag or buttons, small/medium/wide, hide/show, compact or expanded, saved to the account
- [x] Notifications: Windows notifications in the desktop app, browser notifications when Web Push isn't already showing them
- [x] Tests: 86 API, 4 voice server, 12 local agent, 41 web unit tests; Rust `cargo clippy -D warnings`; browser run with a simulated microphone covering push-to-talk, pairing a real agent process, removing it, Home customisation and phone width

## Gate

1. **Spoken replies start in under 1.5 seconds on Tarun's PC.** Each turn shows "Answered in N s" (end of your speech to first sound), and the agent logs `first audio after N ms`. With stand-in engines the pipeline adds 0.3 s. On the real PC the time is mostly Whisper plus the model's first sentence. The likely numbers (not measured, because the build environment can't download models) are about 0.3 s for `base.en` on the CPU and about 0.5 to 0.8 s for Qwen3 14B's first sentence on the RX 9060 XT. **Needs checking on the PC.**
2. **Voice can do everything chat can.** True by construction: a spoken turn is a normal chat turn (same orchestrator, memory, tools and approval rules) with `voice: true`. Covered by API tests and the browser run, and the turn appears in chat history.

## Not yet verified

- Real Whisper, Piper and openWakeWord models, a real microphone and speaker, and the Windows build of the desktop app. None of these could be downloaded or run in the build environment. CI compiles the desktop app on Linux; the Windows installer is built on the PC (README › Windows app).

## Left for later

- Training a "Hey NEXUS" wake word.
- Streaming speech recognition (partial transcripts while you talk).
- A signed Windows installer and auto-update.
- The voice picker (more Piper voices) in Settings.
