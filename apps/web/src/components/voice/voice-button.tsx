"use client";

import { useQuery } from "@tanstack/react-query";
import { Mic } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DeviceInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useVoice } from "./voice-provider";

/** Push to talk. */
export function VoiceButton({ className }: { className?: string }) {
  const [s, c] = useVoice();
  const live = s.phase === "listening";
  return (
    <button
      onClick={() => void c.press()}
      className={cn("relative rounded-lg p-2 text-muted hover:bg-raised hover:text-text", live && "text-danger", className)}
      aria-label={live ? "Finish speaking" : "Talk to NEXUS (Ctrl+Shift+Space)"}
      title="Talk to NEXUS (Ctrl+Shift+Space)"
    >
      <Mic className="size-5" />
    </button>
  );
}

const DEVICE_MIC: Record<string, string> = { wake: "listening for the wake word", listening: "listening", thinking: "thinking", speaking: "speaking" };

/** Always visible when any microphone is open: this browser, or a paired PC. */
export function MicIndicator() {
  const [s] = useVoice();
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<DeviceInfo[]>("/devices"), refetchInterval: 10_000 });
  const live = (devices.data ?? []).filter((d) => d.online && d.mic !== "off");
  if (!s.micOn && !live.length) return null;
  const text = s.micOn ? "Mic on in this browser" : `${live[0].name}: ${DEVICE_MIC[live[0].mic] ?? "mic on"}`;
  return (
    <Link
      href="/settings/devices"
      className="flex items-center gap-1.5 rounded-full border border-danger/40 bg-danger/10 px-2.5 py-1 text-xs text-danger"
      aria-live="polite"
    >
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-danger opacity-60" />
        <span className="relative inline-flex size-2 rounded-full bg-danger" />
      </span>
      <span className="hidden max-w-[180px] truncate sm:inline">{text}</span>
      <span className="sr-only sm:hidden">{text}</span>
    </Link>
  );
}
