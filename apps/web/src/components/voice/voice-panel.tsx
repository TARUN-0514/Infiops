"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Mic, Square, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { speakable } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { VoicePhase } from "@/lib/voice/controller";
import { useVoice } from "./voice-provider";

const LABEL: Record<VoicePhase, string> = {
  idle: "",
  listening: "Listening…",
  transcribing: "Got it…",
  thinking: "Thinking…",
  speaking: "Speaking. Talk to interrupt.",
};

/** Floating panel that shows what NEXUS heard and is saying. */
export function VoicePanel() {
  const [s, c] = useVoice();
  const [dismissed, setDismissed] = useState(false);
  const active = s.phase !== "idle";
  useEffect(() => {
    if (active) setDismissed(false);
  }, [active]);
  const show = active || (!dismissed && (s.heard || s.error));
  return (
    <AnimatePresence>
      {show && (
        <motion.section
          role="status"
          aria-live="polite"
          aria-label="Voice"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-md rounded-2xl border border-border bg-surface/95 p-4 shadow-xl backdrop-blur sm:inset-x-auto sm:right-6 sm:w-[380px]"
        >
          <div className="flex items-start gap-3">
            <button
              onClick={() => void c.press()}
              className={cn(
                "relative grid size-11 shrink-0 place-items-center rounded-full",
                s.phase === "listening" ? "bg-danger text-white" : "bg-accent text-accent-fg",
              )}
              aria-label={s.phase === "listening" ? "Finish speaking" : s.phase === "idle" ? "Talk again" : "Interrupt and talk"}
            >
              {s.phase === "listening" && <span className="absolute inset-0 animate-ping rounded-full bg-danger/40" aria-hidden />}
              {s.phase === "transcribing" || s.phase === "thinking" ? <Loader2 className="size-5 animate-spin" /> : <Mic className="size-5" />}
            </button>
            <div className="min-w-0 flex-1 text-sm">
              <p className="text-xs font-medium text-muted">{LABEL[s.phase] || (s.error ? "Voice" : "Done")}</p>
              {s.heard && <p className="mt-1 font-medium">“{s.heard}”</p>}
              {s.reply && <p className="mt-1 line-clamp-6 text-muted">{speakable(s.reply)}</p>}
              {s.waitingApproval && (
                <p className="mt-1 text-xs text-warn">
                  Waiting for your approval.{" "}
                  {s.conversationId && <Link className="underline" href={`/assistant?c=${s.conversationId}`}>Review it</Link>}
                </p>
              )}
              {s.error && <p className="mt-1 text-danger">{s.error}</p>}
              <p className="mt-2 text-xs text-muted">
                {s.latencyMs !== null && s.phase !== "listening" ? `Answered in ${(s.latencyMs / 1000).toFixed(1)} s · ` : ""}
                {s.fallbackVoice ? "Browser voice (voice server is off) · " : ""}
                {s.conversationId ? <Link className="hover:text-text hover:underline" href={`/assistant?c=${s.conversationId}`}>Open in chat</Link> : "Ctrl+Shift+Space to talk"}
              </p>
            </div>
            {active ? (
              <button onClick={() => c.close()} className="rounded-lg p-1.5 text-muted hover:bg-raised" aria-label="Stop voice">
                <Square className="size-4" />
              </button>
            ) : (
              <button onClick={() => setDismissed(true)} className="rounded-lg p-1.5 text-muted hover:bg-raised" aria-label="Close">
                <X className="size-4" />
              </button>
            )}
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
