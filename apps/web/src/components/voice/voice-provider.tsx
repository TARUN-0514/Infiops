"use client";

import { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import { ApiError, api, rawFetch } from "@/lib/api";
import { onDesktopPushToTalk } from "@/lib/desktop";
import { streamChat } from "@/lib/stream";
import { BrowserMic, BrowserPlayer } from "@/lib/voice/audio";
import { VoiceController, VoiceUnavailable, type VoiceState } from "@/lib/voice/controller";
import { VoicePanel } from "./voice-panel";

const Ctx = createContext<VoiceController | null>(null);

function makeController() {
  return new VoiceController({
    mic: new BrowserMic(),
    player: new BrowserPlayer(),
    transcribe: async (wav) => {
      const form = new FormData();
      form.append("file", new Blob([wav], { type: "audio/wav" }), "speech.wav");
      try {
        const res = await rawFetch("/voice/transcribe", { method: "POST", form });
        return ((await res.json()) as { text: string }).text;
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) throw new Error(`${e.message}`);
        throw e;
      }
    },
    speak: async (text) => {
      try {
        const res = await rawFetch("/voice/speak", { method: "POST", body: { text } });
        return await res.arrayBuffer();
      } catch (e) {
        if (e instanceof ApiError && (e.status === 503 || e.status === 502)) throw new VoiceUnavailable(e.message);
        throw e;
      }
    },
    newConversation: async () => (await api<{ id: string }>("/chat/conversations", { method: "POST" })).id,
    ask: (cid, text, onEvent, signal) => streamChat(cid, { text, voice: true }, onEvent, signal),
  });
}

export function VoiceProvider({ children }: { children: React.ReactNode }) {
  const controller = useMemo(makeController, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.code === "Space") {
        e.preventDefault();
        void controller.press();
      } else if (e.key === "Escape" && controller.state.phase !== "idle") {
        controller.close();
      }
    };
    window.addEventListener("keydown", onKey);
    const offDesktop = onDesktopPushToTalk(() => void controller.press());
    return () => {
      window.removeEventListener("keydown", onKey);
      offDesktop();
      controller.close();
    };
  }, [controller]);
  return (
    <Ctx.Provider value={controller}>
      {children}
      <VoicePanel />
    </Ctx.Provider>
  );
}

export function useVoice(): [VoiceState, VoiceController] {
  const c = useContext(Ctx);
  if (!c) throw new Error("useVoice outside VoiceProvider");
  const state = useSyncExternalStore(c.subscribe, c.getState, c.getState);
  return [state, c];
}
