"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, Laptop, MicOff, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { useVoice } from "@/components/voice/voice-provider";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isDesktopApp } from "@/lib/desktop";
import type { DeviceInfo, VoiceServerStatus, VoiceStatus } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

function message(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong. Try again.";
}

function ServerRow({ label, s }: { label: string; s: VoiceServerStatus }) {
  return (
    <li className="flex items-start gap-2 py-2">
      {s.ready ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> : <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />}
      <div className="min-w-0 text-sm">
        <p>
          {label}: <span className={s.ready ? "text-good" : "text-danger"}>{s.ready ? `working (${s.ms} ms)` : "not working"}</span>
          {s.voice && s.ready ? <span className="text-muted"> · {s.voice}</span> : null}
        </p>
        <p className="break-all text-xs text-muted">{s.ready ? s.url : s.error}</p>
      </div>
    </li>
  );
}

export function VoiceStatusCard() {
  const q = useQuery({ queryKey: ["voice", "status"], queryFn: () => api<VoiceStatus>("/voice/status"), staleTime: 30_000 });
  const [, voice] = useVoice();
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <CardTitle>Voice</CardTitle>
        <Button variant="secondary" className="h-8 px-3" onClick={() => void q.refetch()} loading={q.isFetching}>Test again</Button>
      </div>
      <p className="mt-1 text-sm text-muted">Speech recognition (Whisper) and the voice (Piper) run on your PC. Each is tested with a real call.</p>
      {q.isLoading ? <Skeleton className="mt-3 h-20" /> : q.isError ? <div className="mt-3"><Alert>{message(q.error)}</Alert></div> : q.data && (
        <>
          {!q.data.enabled && <div className="mt-3"><Alert>Voice is turned off (NEXUS_VOICE_ENABLED=false).</Alert></div>}
          <ul className="mt-2 divide-y divide-border">
            <ServerRow label="Speech recognition" s={q.data.stt} />
            <ServerRow label="Voice" s={q.data.tts} />
          </ul>
          {(!q.data.stt.ready || !q.data.tts.ready) && (
            <p className="mt-2 text-xs text-muted">
              Start the voice server with <code className="rounded bg-raised px-1">docker compose up -d voice</code>. The first start downloads the models (about 200 MB). For faster speech recognition on your Radeon GPU, see the Voice section of the README.
            </p>
          )}
        </>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button className="h-9" onClick={() => void voice.press()}>Try it</Button>
        <p className="text-xs text-muted">Or press Ctrl+Shift+Space on any page. Talk over NEXUS to interrupt it.</p>
      </div>
    </Card>
  );
}

function useTz() {
  return useAuth().user?.timezone ?? "UTC";
}

function PairCode() {
  const tz = useTz();
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const make = useMutation({ mutationFn: () => api<{ code: string; expires_at: string }>("/devices/pair-code", { method: "POST" }), onSuccess: setCode });
  const command = code ? `nexus-agent pair --code ${code.code}` : "";
  return (
    <div className="rounded-lg border border-border p-3">
      {code ? (
        <div className="space-y-2 text-sm">
          <p>On your PC, run this in PowerShell:</p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-bg px-2 py-1.5 font-mono text-xs">{command}</code>
            <Button
              variant="ghost"
              className="h-8 px-2"
              aria-label="Copy command"
              onClick={() => void navigator.clipboard.writeText(command).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}
            >
              <Copy className="size-4" aria-hidden />{copied ? "Copied" : ""}
            </Button>
          </div>
          <p className="text-xs text-muted">The code works once and expires at {formatDateTime(code.expires_at, tz)}. Add <code>--server http://YOUR-PC:8000</code> if NEXUS runs elsewhere.</p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted">Pair the NEXUS local agent on your Windows PC for the wake word and hands-free voice.</p>
          <Button className="h-9" onClick={() => make.mutate()} loading={make.isPending}>Pair a PC</Button>
        </div>
      )}
      {make.isError && <div className="mt-2"><Alert>{message(make.error)}</Alert></div>}
    </div>
  );
}

const MIC_TEXT: Record<DeviceInfo["mic"], string> = {
  off: "Microphone off",
  wake: "Listening for the wake word",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

function Toggle({ label, hint, checked, disabled, onChange }: { label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className={cn("flex items-start gap-3 text-sm", disabled && "opacity-50")}>
      <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>
        {label}
        <span className="block text-xs text-muted">{hint}</span>
      </span>
    </label>
  );
}

function DeviceRow({ d }: { d: DeviceInfo }) {
  const tz = useTz();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["devices"] });
  const patch = useMutation({ mutationFn: (body: Partial<DeviceInfo["settings"]>) => api(`/devices/${d.id}`, { method: "PATCH", body }), onSuccess: refresh });
  const stop = useMutation({ mutationFn: () => api(`/devices/${d.id}/stop`, { method: "POST" }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api(`/devices/${d.id}`, { method: "DELETE" }), onSuccess: refresh });
  const hasWake = d.capabilities.wake_word === true;
  const micOpen = d.online && d.mic !== "off";
  return (
    <li className="space-y-3 py-3">
      <div className="flex items-start gap-3">
        <Laptop className="mt-0.5 size-5 shrink-0 text-muted" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{d.name}</p>
          <p className="text-xs text-muted">
            {d.online ? <span className="text-good">Connected</span> : "Offline"}
            {d.online ? ` · ${MIC_TEXT[d.mic]}` : d.last_seen_at ? ` · last seen ${formatDateTime(d.last_seen_at, tz)}` : ""}
            {d.capabilities.version ? ` · agent ${String(d.capabilities.version)}` : ""}
          </p>
        </div>
        {micOpen && (
          <Button variant="danger" className="h-8 px-3" onClick={() => stop.mutate()} loading={stop.isPending}>
            <MicOff className="size-4" aria-hidden />Stop listening
          </Button>
        )}
      </div>
      <div className="space-y-2 pl-8">
        <Toggle
          label="Wake word"
          hint={hasWake ? `Say “${String(d.capabilities.wake_word_model || "hey jarvis").replace(/_/g, " ")}” to start talking. Detected on the PC; nothing is sent until it hears it.` : "Install the agent's audio extras to use a wake word."}
          checked={d.settings.wake_word}
          disabled={!hasWake && !d.settings.wake_word}
          onChange={(v) => patch.mutate({ wake_word: v })}
        />
        <Toggle
          label="Hands-free"
          hint="Keep listening for a follow-up after each answer, without the wake word."
          checked={d.settings.hands_free}
          onChange={(v) => patch.mutate({ hands_free: v })}
        />
        {patch.isError && <Alert>{message(patch.error)}</Alert>}
        <div>
          {confirm ? (
            <Button variant="danger" className="h-8 px-3" onClick={() => remove.mutate()} loading={remove.isPending}>Remove this PC</Button>
          ) : (
            <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setConfirm(true)}><Trash2 className="size-3.5" aria-hidden />Remove…</Button>
          )}
        </div>
      </div>
    </li>
  );
}

export function DevicesCard() {
  const q = useQuery({ queryKey: ["devices"], queryFn: () => api<DeviceInfo[]>("/devices"), refetchInterval: 5_000 });
  return (
    <Card>
      <CardTitle>Paired PCs</CardTitle>
      <div className="mt-3"><PairCode /></div>
      {q.isLoading ? <Skeleton className="mt-3 h-16" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load devices.</Alert></div> : !q.data?.length ? (
        <p className="mt-3 text-sm text-muted">No PC paired yet.</p>
      ) : (
        <ul className="mt-2 divide-y divide-border">{q.data.map((d) => <DeviceRow key={d.id} d={d} />)}</ul>
      )}
    </Card>
  );
}

export function DesktopAppCard() {
  const inApp = isDesktopApp();
  return (
    <Card>
      <CardTitle>Windows app</CardTitle>
      {inApp ? (
        <p className="mt-2 text-sm text-muted">You&apos;re using the NEXUS Windows app. Ctrl+Shift+Space talks to NEXUS from anywhere on your PC, and notifications appear in Windows.</p>
      ) : (
        <p className="mt-2 text-sm text-muted">
          The Windows app opens NEXUS in its own window with a tray icon, a Ctrl+Shift+Space shortcut that works from any app, Windows notifications, and it starts the local agent for you. Build it with the steps in the README (Windows app section).
        </p>
      )}
    </Card>
  );
}
