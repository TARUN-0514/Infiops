"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Check, Flame, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Habit, type HabitList, lastDays } from "@/lib/fitness";
import { cn } from "@/lib/utils";
import { useRefreshFitness } from "./hooks";

const SPAN = 14;

function HabitRow({ h, days }: { h: Habit; days: string[] }) {
  const refresh = useRefreshFitness();
  const done = new Set(h.days);
  const tick = useMutation({ mutationFn: (v: { day: string; done: boolean }) => api(`/habits/${h.id}/days`, { method: "PUT", body: v }), onSuccess: refresh });
  const archive = useMutation({ mutationFn: () => api(`/habits/${h.id}`, { method: "PATCH", body: { name: h.name, per_week: h.per_week, archived: !h.archived } }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api(`/habits/${h.id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <li className={cn("py-3", h.archived && "opacity-60")}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-sm font-medium">{h.name}</p>
        {!h.archived && (
          <span className="flex items-center gap-1 text-xs text-muted">
            <Flame className={cn("size-3.5", h.streak > 0 && "text-warn")} />{h.streak} day{h.streak === 1 ? "" : "s"} · {h.this_week}/{h.per_week} this week
          </span>
        )}
        <button onClick={() => archive.mutate()} className="rounded p-1.5 text-muted hover:bg-raised" aria-label={h.archived ? `Restore ${h.name}` : `Archive ${h.name}`}>
          {h.archived ? <ArchiveRestore className="size-3.5" /> : <Archive className="size-3.5" />}
        </button>
        <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${h.name}`}><Trash2 className="size-3.5" /></button>
      </div>
      {!h.archived && (
        <div className="mt-2 grid grid-cols-7 gap-1 sm:grid-cols-[repeat(14,minmax(0,1fr))]">
          {days.map((d) => {
            const on = done.has(d);
            return (
              <button
                key={d}
                onClick={() => tick.mutate({ day: d, done: !on })}
                aria-pressed={on}
                aria-label={`${h.name}, ${dayLabel(d, { weekday: "long", day: "numeric", month: "short" })}`}
                className={cn("flex h-9 flex-col items-center justify-center rounded-md border text-[10px] leading-none", on ? "border-good/40 bg-good/20 text-good" : "border-border text-muted hover:bg-raised")}
              >
                <span>{dayLabel(d, { weekday: "narrow" })}</span>
                {on ? <Check className="mt-0.5 size-3" /> : <span className="mt-0.5">{Number(d.slice(8))}</span>}
              </button>
            );
          })}
        </div>
      )}
      {(tick.isError || archive.isError || remove.isError) && <div className="mt-2"><Alert>{errorText(tick.error ?? archive.error ?? remove.error)}</Alert></div>}
    </li>
  );
}

export function Habits() {
  const refresh = useRefreshFitness();
  const q = useQuery({ queryKey: ["habits"], queryFn: () => api<HabitList>("/habits?days=28") });
  const [name, setName] = useState("");
  const [perWeek, setPerWeek] = useState("7");
  const add = useMutation({ mutationFn: () => api("/habits", { method: "POST", body: { name: name.trim(), per_week: Number(perWeek) } }), onSuccess: () => { setName(""); refresh(); } });
  const days = q.data ? lastDays(q.data.today, SPAN) : [];
  const live = q.data?.habits.filter((h) => !h.archived) ?? [];
  const archived = q.data?.habits.filter((h) => h.archived) ?? [];
  return (
    <Card>
      <CardTitle>Habits</CardTitle>
      <p className="mt-1 text-sm text-muted">Tap a day to tick it. Streaks count today once it&apos;s ticked, so an unticked today doesn&apos;t break yours yet.</p>
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) add.mutate(); }} className="mt-4 flex flex-wrap gap-2">
        <label htmlFor="habit-name" className="sr-only">New habit</label>
        <input id="habit-name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="New habit, e.g. 10k steps" className={cn(inputCls, "min-w-0 flex-1 basis-full sm:basis-auto")} />
        <label htmlFor="habit-target" className="sr-only">Times a week</label>
        <select id="habit-target" value={perWeek} onChange={(e) => setPerWeek(e.target.value)} className={inputCls}>
          {[7, 6, 5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n === 7 ? "Every day" : `${n} times a week`}</option>)}
        </select>
        <Button type="submit" className="h-9" loading={add.isPending} disabled={!name.trim()}>Add habit</Button>
      </form>
      {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      {q.isLoading ? <Skeleton className="mt-4 h-32" /> : q.isError ? <div className="mt-4"><Alert>Couldn&apos;t load habits.</Alert></div> : !q.data?.habits.length ? (
        <div className="mt-4"><Empty>No habits yet. Add one above.</Empty></div>
      ) : (
        <>
          <ul className="mt-2 divide-y divide-border">{live.map((h) => <HabitRow key={h.id} h={h} days={days} />)}</ul>
          {archived.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-muted">Archived ({archived.length})</summary>
              <ul className="divide-y divide-border">{archived.map((h) => <HabitRow key={h.id} h={h} days={days} />)}</ul>
            </details>
          )}
        </>
      )}
    </Card>
  );
}
