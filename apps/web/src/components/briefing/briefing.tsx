"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, RefreshCw, Volume2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { speakable } from "@/lib/format";
import type { Briefing, BriefingSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

type Today = { date: string; briefing: Briefing | null; settings: BriefingSettings };

export function useToday() {
  return useQuery({ queryKey: ["briefing", "today"], queryFn: () => api<Today>("/briefings/today") });
}

function ListenButton({ text }: { text: string }) {
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const utter = useRef<SpeechSynthesisUtterance | null>(null);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  if (!supported) return null;
  const toggle = () => {
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(speakable(text));
    u.rate = 1.02;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    utter.current = u;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    setSpeaking(true);
  };
  return (
    <Button variant="secondary" onClick={toggle} aria-pressed={speaking}>
      {speaking ? <Pause className="size-4" aria-hidden /> : <Volume2 className="size-4" aria-hidden />}
      {speaking ? "Stop" : "Listen"}
    </Button>
  );
}

export function BriefingToday() {
  const qc = useQueryClient();
  const today = useToday();
  const [error, setError] = useState<string | null>(null);
  const generate = useMutation({
    mutationFn: (regenerate: boolean) => api<Briefing>("/briefings/today", { method: "POST", body: { regenerate } }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["briefing"] });
      void qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't write the briefing."),
  });
  const b = today.data?.briefing;
  useEffect(() => {
    if (b && !b.read_at) void api(`/briefings/${b.id}/read`, { method: "POST" }).catch(() => undefined);
  }, [b]);

  if (today.isLoading) return <Skeleton className="h-64" />;
  if (today.isError || !today.data) return <Alert>Couldn&apos;t load today&apos;s briefing.</Alert>;
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted">{dayLabel(today.data.date, { weekday: "long", day: "numeric", month: "long" })}</p>
          <CardTitle className="mt-0.5 text-lg">Morning briefing</CardTitle>
        </div>
        <div className="flex gap-2">
          {b && <ListenButton text={b.content} />}
          <Button variant={b ? "ghost" : "primary"} onClick={() => generate.mutate(Boolean(b))} loading={generate.isPending}>
            <RefreshCw className="size-4" aria-hidden />
            {b ? "Rewrite" : "Write it now"}
          </Button>
        </div>
      </div>
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      {b ? (
        <>
          <div className="mt-5 text-[15px] leading-relaxed">
            <Markdown text={b.content} />
          </div>
          <p className="mt-6 border-t border-border pt-3 text-xs text-muted">
            Written {b.written_by_model ? `by ${b.model} on your PC` : "without a model (the local model was offline), from the same facts"} at{" "}
            {new Date(b.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}. Built only from your calendar, tasks and email.
          </p>
        </>
      ) : (
        <p className="mt-4 text-sm text-muted">
          {today.data.settings.enabled
            ? `Today's briefing arrives at ${today.data.settings.time}. You can write it now instead.`
            : "Scheduled briefings are off. You can still write one now."}
        </p>
      )}
    </Card>
  );
}

type Toggle = "enabled" | "midday" | "evening";
type TimeKey = "time" | "midday_time" | "evening_time";

function ScheduleRow({ s, on, at, label, save }: { s: BriefingSettings; on: Toggle; at: TimeKey; label: string; save: (b: Partial<BriefingSettings>) => void }) {
  const [time, setTime] = useState(s[at]);
  useEffect(() => setTime(s[at]), [s, at]);
  const id = `sched-${at}`;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex min-w-36 flex-1 items-center gap-2">
        <input type="checkbox" checked={s[on]} onChange={(e) => save({ [on]: e.target.checked })} className="size-4 accent-accent" />
        {label}
      </label>
      <label htmlFor={id} className="sr-only">{label} time</label>
      <input id={id} type="time" value={time} disabled={!s[on]} onChange={(e) => setTime(e.target.value)} className="h-9 rounded-lg border border-border bg-surface px-2 disabled:opacity-50" />
      {time !== s[at] && <Button variant="secondary" className="h-9" onClick={() => save({ [at]: time })}>Save</Button>}
    </div>
  );
}

export function BriefingSettingsCard() {
  const qc = useQueryClient();
  const today = useToday();
  const [saved, setSaved] = useState(false);
  const s = today.data?.settings;
  const save = useMutation({
    mutationFn: (body: Partial<BriefingSettings>) => api<BriefingSettings>("/briefings/settings", { method: "PUT", body }),
    onSuccess: () => {
      setSaved(true);
      void qc.invalidateQueries({ queryKey: ["briefing"] });
    },
  });
  if (!s) return null;
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Schedule</CardTitle>
        {saved && !save.isPending && <span className="text-xs text-good">Saved</span>}
      </div>
      <div className="mt-3 space-y-3 text-sm">
        <ScheduleRow s={s} on="enabled" at="time" label="Morning briefing" save={save.mutate} />
        <ScheduleRow s={s} on="midday" at="midday_time" label="Midday check-in" save={save.mutate} />
        <ScheduleRow s={s} on="evening" at="evening_time" label="Evening review" save={save.mutate} />
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={s.monthly} onChange={(e) => save.mutate({ monthly: e.target.checked })} className="size-4 accent-accent" />
          Monthly report on the 1st
        </label>
        <label className="flex items-center gap-2 border-t border-border pt-3">
          <input type="checkbox" checked={s.push} onChange={(e) => save.mutate({ push: e.target.checked })} className="size-4 accent-accent" />
          Send a notification when each is ready
        </label>
        {save.isError && <Alert>Couldn&apos;t save. Check the time and try again.</Alert>}
        <p className="text-xs text-muted">
          Notifications need to be on for this device in <Link href="/settings/integrations" className="text-accent hover:underline">Settings › Integrations</Link>.
        </p>
      </div>
    </Card>
  );
}

const HISTORY_TITLE = { morning: "Earlier briefings", midday: "Earlier check-ins", evening: "Earlier reviews" };

export function BriefingHistory({ kind = "morning" }: { kind?: "morning" | "midday" | "evening" }) {
  const q = useQuery({ queryKey: ["briefing", "history", kind], queryFn: () => api<Briefing[]>(`/briefings?kind=${kind}`) });
  const [open, setOpen] = useState<string | null>(null);
  const day = useToday().data?.date;
  const past = (q.data ?? []).filter((b) => b.for_date !== day);
  return (
    <Card>
      <CardTitle>{HISTORY_TITLE[kind]}</CardTitle>
      {q.isLoading ? <Skeleton className="mt-3 h-16" /> : !past.length ? (
        <p className="mt-2 text-sm text-muted">Past ones will collect here.</p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {past.map((b) => (
            <li key={b.id} className="py-2">
              <button onClick={() => setOpen(open === b.id ? null : b.id)} className={cn("w-full text-left text-sm hover:text-text", open === b.id ? "text-text" : "text-muted")} aria-expanded={open === b.id}>
                {dayLabel(b.for_date, { weekday: "long", day: "numeric", month: "short" })}
              </button>
              {open === b.id && <div className="mt-2 text-sm"><Markdown text={b.content} /></div>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function BriefingHomeCard() {
  const today = useToday();
  const b = today.data?.briefing;
  const first = b?.content.split("\n").find((l) => l.trim() && !l.startsWith("#"))?.replace(/\*\*/g, "");
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Morning briefing</CardTitle>
        <Link href="/briefing" className="text-xs text-accent hover:underline">{b ? "Read" : "Open"}</Link>
      </div>
      {today.isLoading ? <Skeleton className="mt-3 h-12" /> : today.isError ? (
        <div className="mt-3"><Alert>Couldn&apos;t load the briefing.</Alert></div>
      ) : b ? (
        <p className="mt-2 line-clamp-3 text-sm text-muted">{first}</p>
      ) : (
        <p className="mt-2 text-sm text-muted">Arrives at {today.data?.settings.time}. <Link href="/briefing" className="text-accent hover:underline">Write it now</Link></p>
      )}
    </Card>
  );
}
