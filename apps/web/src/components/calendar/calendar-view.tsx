"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Clock, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { EventDialog, newDraft, type Draft } from "@/components/calendar/event-dialog";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { addDays, dayKey, dayLabel, layoutDay, monthGrid, overlapsDay, timeLabel, weekDays, zonedTime } from "@/lib/calendar";
import type { CalendarEvent, CalendarRange, FreeSlot, Task } from "@/lib/types";
import { cn } from "@/lib/utils";

type Mode = "day" | "week" | "month";
const HOUR_PX = 48;

function rangeFor(mode: Mode, key: string): string[] {
  if (mode === "day") return [key];
  if (mode === "week") return weekDays(key);
  return monthGrid(key);
}

function EventChip({ e, tz, onOpen, conflict }: { e: CalendarEvent; tz: string; onOpen: () => void; conflict: boolean }) {
  return (
    <button
      onClick={onOpen}
      className={cn(
        "block w-full truncate rounded px-1.5 py-0.5 text-left text-[11px]",
        e.source === "time_block" ? "bg-good/15 text-good" : "bg-accent/15 text-text",
        conflict && "ring-1 ring-warn",
      )}
    >
      {!e.all_day && <span className="text-muted">{timeLabel(e.starts_at, tz)} </span>}
      {e.title}
    </button>
  );
}

function TimeGrid({ days, events, tz, conflicts, onOpen, onNew }: { days: string[]; events: CalendarEvent[]; tz: string; conflicts: Set<string>; onOpen: (e: CalendarEvent) => void; onNew: (key: string, hour: number) => void }) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = HOUR_PX * 7.5;
  }, []);
  const today = dayKey(new Date(), tz);
  const now = new Date();
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <div className="grid border-b border-border bg-surface" style={{ gridTemplateColumns: `48px repeat(${days.length}, minmax(0,1fr))` }}>
        <div />
        {days.map((d) => (
          <div key={d} className={cn("border-l border-border px-1 py-1.5 text-center text-xs", d === today ? "text-accent" : "text-muted")}>
            {dayLabel(d, { weekday: "short", day: "numeric" })}
            <div className="mt-1 space-y-0.5">
              {events.filter((e) => e.all_day && overlapsDay(e, d, tz)).map((e) => (
                <EventChip key={e.id} e={e} tz={tz} onOpen={() => onOpen(e)} conflict={false} />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div ref={scroller} className="max-h-[65vh] overflow-y-auto">
        <div className="relative grid" style={{ gridTemplateColumns: `48px repeat(${days.length}, minmax(0,1fr))`, height: HOUR_PX * 24 }}>
          <div className="relative">
            {Array.from({ length: 24 }, (_, h) => (
              <span key={h} className="absolute right-1 -translate-y-1/2 text-[10px] text-muted" style={{ top: h * HOUR_PX }}>
                {h === 0 ? "" : `${String(h).padStart(2, "0")}:00`}
              </span>
            ))}
          </div>
          {days.map((d) => (
            <div key={d} className="relative border-l border-border">
              {Array.from({ length: 24 }, (_, h) => (
                <button
                  key={h}
                  onClick={() => onNew(d, h)}
                  className="absolute inset-x-0 border-t border-border/60 hover:bg-raised/40"
                  style={{ top: h * HOUR_PX, height: HOUR_PX }}
                  aria-label={`New event ${dayLabel(d)} at ${h}:00`}
                />
              ))}
              {d === today && (
                <div className="pointer-events-none absolute inset-x-0 z-10 h-px bg-danger" style={{ top: ((now.getTime() - zonedTime(d, tz).getTime()) / 86_400_000) * HOUR_PX * 24 }} />
              )}
              {layoutDay(events, d, tz).map((p) => (
                <button
                  key={p.event.id}
                  onClick={() => onOpen(p.event)}
                  className={cn(
                    "absolute z-[5] overflow-hidden rounded-md border px-1.5 py-0.5 text-left text-[11px] leading-tight",
                    p.event.source === "time_block" ? "border-good/40 bg-good/15" : "border-accent/40 bg-accent/20",
                    conflicts.has(p.event.id) && "border-warn",
                  )}
                  style={{ top: p.top * HOUR_PX * 24, height: Math.max(p.height * HOUR_PX * 24, 18), left: `calc(${(p.col / p.cols) * 100}% + 2px)`, width: `calc(${100 / p.cols}% - 4px)` }}
                >
                  <span className="block truncate font-medium">{p.event.title}</span>
                  <span className="block truncate text-muted">{timeLabel(p.event.starts_at, tz)}–{timeLabel(p.event.ends_at, tz)}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MonthGrid({ anchor, events, tz, conflicts, onOpen, onDay }: { anchor: string; events: CalendarEvent[]; tz: string; conflicts: Set<string>; onOpen: (e: CalendarEvent) => void; onDay: (key: string) => void }) {
  const days = monthGrid(anchor);
  const month = anchor.slice(0, 7);
  const today = dayKey(new Date(), tz);
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <div className="grid grid-cols-7 border-b border-border bg-surface text-center text-xs text-muted">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="py-1.5">{d}</div>)}
      </div>
      <div className="grid grid-cols-7">
        {days.map((d) => {
          const list = events.filter((e) => overlapsDay(e, d, tz));
          return (
            <div key={d} className={cn("min-h-24 border-b border-l border-border p-1", d.slice(0, 7) !== month && "bg-bg/40 text-muted")}>
              <button onClick={() => onDay(d)} className={cn("mb-1 rounded px-1 text-xs hover:bg-raised", d === today && "bg-accent text-accent-fg")}>{Number(d.slice(8))}</button>
              <div className="space-y-0.5">
                {list.slice(0, 3).map((e) => <EventChip key={e.id} e={e} tz={tz} onOpen={() => onOpen(e)} conflict={conflicts.has(e.id)} />)}
                {list.length > 3 && <button onClick={() => onDay(d)} className="px-1 text-[11px] text-muted hover:text-text">+{list.length - 3} more</button>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FreeTime({ tz, initialDay }: { tz: string; initialDay: string }) {
  const qc = useQueryClient();
  const [day, setDay] = useState(initialDay);
  const [minutes, setMinutes] = useState(60);
  const [taskId, setTaskId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setDay(initialDay), [initialDay]);
  const slots = useQuery({ queryKey: ["calendar", "free", day, minutes], queryFn: () => api<FreeSlot[]>(`/calendar/free-slots?day=${day}&minutes=${minutes}`) });
  const tasks = useQuery({ queryKey: ["tasks", "open-top"], queryFn: () => api<Task[]>("/tasks?status=todo&status=in_progress&top_level=true") });
  const block = useMutation({
    mutationFn: (start: string) => api<CalendarEvent>("/calendar/time-block", { method: "POST", body: { task_id: taskId, starts_at: start, minutes } }),
    onSuccess: (e) => {
      setNotice(`Blocked ${timeLabel(e.starts_at, tz)}–${timeLabel(e.ends_at, tz)} for ${e.title.replace("Focus: ", "")}.`);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["calendar"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't block the time."),
  });
  return (
    <Card>
      <CardTitle className="flex items-center gap-2"><Clock className="size-4 text-accent" aria-hidden />Free time</CardTitle>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <label className="block">
          <span className="text-xs text-muted">Day</span>
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-border bg-surface px-2" />
        </label>
        <label className="block">
          <span className="text-xs text-muted">At least</span>
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="mt-1 h-9 w-full rounded-lg border border-border bg-surface px-2">
            {[30, 45, 60, 90, 120].map((m) => <option key={m} value={m}>{m} min</option>)}
          </select>
        </label>
      </div>
      <label className="mt-2 block text-sm">
        <span className="text-xs text-muted">Block time for a task</span>
        <select value={taskId} onChange={(e) => setTaskId(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-border bg-surface px-2">
          <option value="">Choose a task…</option>
          {tasks.data?.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
        </select>
      </label>
      {notice && <div className="mt-3"><Alert tone="good">{notice}</Alert></div>}
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      <p className="mt-3 text-xs text-muted">Between 09:00 and 18:00</p>
      {slots.isLoading ? <Skeleton className="mt-2 h-16" /> : slots.isError ? <Alert>Couldn&apos;t find free time.</Alert> : !slots.data?.length ? (
        <p className="mt-2 text-sm text-muted">No free block that long.</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {slots.data.map((s) => (
            <li key={s.start} className="flex items-center justify-between gap-2 text-sm">
              <span>{timeLabel(s.start, tz)}–{timeLabel(s.end, tz)} <span className="text-xs text-muted">({Math.floor(s.minutes / 60) ? `${Math.floor(s.minutes / 60)} h ` : ""}{s.minutes % 60 ? `${s.minutes % 60} min` : ""})</span></span>
              <Button variant="secondary" className="h-7 px-2 text-xs" disabled={!taskId} loading={block.isPending && block.variables === s.start} onClick={() => block.mutate(s.start)}>
                Block
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function CalendarView() {
  const { user } = useAuth();
  const tz = user?.timezone ?? "UTC";
  const [mode, setMode] = useState<Mode>("week");
  const [anchor, setAnchor] = useState(() => dayKey(new Date(), tz));
  const [editing, setEditing] = useState<Draft | null>(null);
  useEffect(() => {
    if (window.matchMedia("(max-width: 640px)").matches) setMode("day");
  }, []);
  const days = rangeFor(mode, anchor);
  const start = zonedTime(days[0], tz).toISOString();
  const end = zonedTime(addDays(days[days.length - 1], 1), tz).toISOString();
  const q = useQuery({
    queryKey: ["calendar", "range", start, end],
    queryFn: () => api<CalendarRange>(`/calendar/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  });
  const conflicts = useMemo(() => new Set((q.data?.conflicts ?? []).flat()), [q.data]);
  const step = mode === "day" ? 1 : mode === "week" ? 7 : 0;
  const move = (dir: number) => {
    if (step) setAnchor(addDays(anchor, dir * step));
    else {
      const [y, m] = anchor.split("-").map(Number);
      const next = new Date(Date.UTC(y, m - 1 + dir, 1));
      setAnchor(next.toISOString().slice(0, 10));
    }
  };
  const title =
    mode === "month"
      ? new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${anchor}T00:00:00Z`))
      : mode === "week"
        ? `${dayLabel(days[0], { day: "numeric", month: "short" })} – ${dayLabel(days[6], { day: "numeric", month: "short", year: "numeric" })}`
        : dayLabel(anchor, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <Button variant="secondary" className="h-9 px-3" onClick={() => setAnchor(dayKey(new Date(), tz))}>Today</Button>
            <Button variant="ghost" className="h-9 px-2" onClick={() => move(-1)} aria-label="Previous"><ChevronLeft className="size-4" /></Button>
            <Button variant="ghost" className="h-9 px-2" onClick={() => move(1)} aria-label="Next"><ChevronRight className="size-4" /></Button>
            <h2 className="ml-1 text-base font-semibold">{title}</h2>
          </div>
          <div className="flex items-center gap-2">
            <div role="tablist" aria-label="Calendar view" className="flex rounded-lg border border-border p-0.5">
              {(["day", "week", "month"] as Mode[]).map((m) => (
                <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={cn("rounded-md px-3 py-1 text-sm capitalize", mode === m ? "bg-accent/15 text-text" : "text-muted hover:text-text")}>
                  {m}
                </button>
              ))}
            </div>
            <Button className="h-9" onClick={() => setEditing(newDraft(mode === "day" ? anchor : dayKey(new Date(), tz), tz))}>
              <Plus className="size-4" aria-hidden /> Event
            </Button>
          </div>
        </div>
        {q.data && !q.data.google_connected && (
          <p className="text-xs text-muted">
            Showing events saved in NEXUS. <Link href="/settings/integrations" className="text-accent hover:underline">Connect Google Calendar</Link> to see your real schedule.
          </p>
        )}
        {q.data && conflicts.size > 0 && (
          <Alert tone="warn">
            <span className="flex items-center gap-2"><AlertTriangle className="size-4" aria-hidden />{q.data.conflicts.length} overlapping event{q.data.conflicts.length > 1 ? "s" : ""} in this view (outlined).</span>
          </Alert>
        )}
        {q.isLoading ? <Skeleton className="h-[60vh]" /> : q.isError || !q.data ? <Alert>Couldn&apos;t load the calendar.</Alert> : mode === "month" ? (
          <MonthGrid anchor={anchor} events={q.data.events} tz={tz} conflicts={conflicts} onOpen={(e) => setEditing(e)} onDay={(d) => { setAnchor(d); setMode("day"); }} />
        ) : (
          <TimeGrid days={days} events={q.data.events} tz={tz} conflicts={conflicts} onOpen={(e) => setEditing(e)} onNew={(d, h) => setEditing(newDraft(d, tz, h))} />
        )}
      </div>
      <div className="space-y-4">
        <FreeTime tz={tz} initialDay={mode === "day" ? anchor : dayKey(new Date(), tz)} />
      </div>
      {editing && <EventDialog event={editing} tz={tz} googleConnected={Boolean(q.data?.google_connected)} onClose={() => setEditing(null)} />}
    </div>
  );
}
