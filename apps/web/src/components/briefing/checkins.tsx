"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { monthLabel } from "@/lib/finance";
import type { Briefing, BriefingSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

export type CheckinKind = "midday" | "evening";
type CheckinsToday = { date: string; settings: BriefingSettings; midday: Briefing | null; evening: Briefing | null };

const META: Record<CheckinKind, { title: string; what: string }> = {
  midday: { title: "Midday check-in", what: "progress so far, what's still due today and the rest of your calendar" },
  evening: { title: "Evening review", what: "what got done, what slipped, habits and a look at tomorrow" },
};

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback;
}

export function WrittenBy({ b, local }: { b: Briefing; local?: boolean }) {
  return (
    <p className="mt-6 border-t border-border pt-3 text-xs text-muted">
      Written {b.written_by_model ? `by ${b.model} on your PC` : "without a model (the local model was offline), from the same facts"} at{" "}
      {new Date(b.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.
      {local && " Includes money and health figures, so it is only ever written locally."}
    </p>
  );
}

export function CheckinPanel({ kind }: { kind: CheckinKind }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["briefing", "checkins"], queryFn: () => api<CheckinsToday>("/checkins/today") });
  const [error, setError] = useState<string | null>(null);
  const write = useMutation({
    mutationFn: (regenerate: boolean) => api<Briefing>(`/checkins/${kind}`, { method: "POST", body: { regenerate } }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["briefing"] });
    },
    onError: (e) => setError(errorMessage(e, "Couldn't write it.")),
  });
  const b = q.data?.[kind] ?? null;
  useEffect(() => {
    if (b && !b.read_at) void api(`/briefings/${b.id}/read`, { method: "POST" }).catch(() => undefined);
  }, [b]);
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError || !q.data) return <Alert>Couldn&apos;t load today&apos;s {META[kind].title.toLowerCase()}.</Alert>;
  const s = q.data.settings;
  const on = s[kind];
  const at = s[`${kind}_time`];
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted">{dayLabel(q.data.date, { weekday: "long", day: "numeric", month: "long" })}</p>
          <CardTitle className="mt-0.5 text-lg">{META[kind].title}</CardTitle>
        </div>
        <Button variant={b ? "ghost" : "primary"} onClick={() => write.mutate(Boolean(b))} loading={write.isPending}>
          <RefreshCw className="size-4" aria-hidden />
          {b ? "Rewrite" : "Write it now"}
        </Button>
      </div>
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      {b ? (
        <>
          <div className="mt-5 text-[15px] leading-relaxed"><Markdown text={b.content} /></div>
          <WrittenBy b={b} />
        </>
      ) : (
        <p className="mt-4 text-sm text-muted">
          Covers {META[kind].what}. {on ? `It arrives at ${at}.` : "Scheduled delivery is off."} You can write it now instead.
        </p>
      )}
    </Card>
  );
}

function lastMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function MonthlyReports() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["briefing", "monthly"], queryFn: () => api<Briefing[]>("/reports/monthly") });
  const [month, setMonth] = useState(lastMonth);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const write = useMutation({
    mutationFn: () => api<Briefing>("/reports/monthly", { method: "POST", body: { month } }),
    onSuccess: (b) => {
      setError(null);
      setOpen(b.id);
      void qc.invalidateQueries({ queryKey: ["briefing", "monthly"] });
    },
    onError: (e) => setError(errorMessage(e, "Couldn't write the report.")),
  });
  const rows = q.data ?? [];
  const shown = rows.find((r) => r.id === open) ?? rows[0];
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <CardTitle className="text-lg">Monthly report</CardTitle>
          <p className="mt-0.5 text-sm text-muted">Tasks, time, habits, goals, money and fitness for a month. Written on the 1st.</p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="report-month" className="sr-only">Month</label>
          <input id="report-month" type="month" value={month} max={new Date().toISOString().slice(0, 7)} onChange={(e) => setMonth(e.target.value)} className="h-9 rounded-lg border border-border bg-surface px-2 text-sm" />
          <Button onClick={() => write.mutate()} loading={write.isPending} disabled={!month}>Write report</Button>
        </div>
      </div>
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      {q.isLoading ? <Skeleton className="mt-5 h-40" /> : q.isError ? (
        <div className="mt-5"><Alert>Couldn&apos;t load reports.</Alert></div>
      ) : !shown ? (
        <p className="mt-5 text-sm text-muted">No monthly reports yet. Your first arrives on the 1st, or write one for any past month now.</p>
      ) : (
        <>
          {rows.length > 1 && (
            <div className="mt-5 flex flex-wrap gap-1" role="tablist" aria-label="Reports">
              {rows.map((r) => (
                <button key={r.id} role="tab" aria-selected={r.id === shown.id} onClick={() => setOpen(r.id)} className={cn("rounded-lg px-2.5 py-1 text-sm", r.id === shown.id ? "bg-accent/15 text-text" : "text-muted hover:bg-raised")}>
                  {monthLabel(r.for_date.slice(0, 7), "short")}
                </button>
              ))}
            </div>
          )}
          <p className="mt-5 text-sm text-muted">{monthLabel(shown.for_date.slice(0, 7))}</p>
          <div className="mt-2 text-[15px] leading-relaxed"><Markdown text={shown.content} /></div>
          <WrittenBy b={shown} local />
        </>
      )}
    </Card>
  );
}
