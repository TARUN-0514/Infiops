"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type Routine, WEEKDAYS, weekdaysLabel } from "@/lib/personal";
import { cn } from "@/lib/utils";
import { useRefreshPersonal } from "./hooks";

type Draft = { name: string; time_of_day: Routine["time_of_day"]; steps: string; weekdays: number[] };
const EMPTY: Draft = { name: "", time_of_day: "morning", steps: "", weekdays: [] };

function Editor({ start, onSave, saving, onCancel }: { start: Draft; onSave: (d: Draft) => void; saving: boolean; onCancel?: () => void }) {
  const [d, setD] = useState(start);
  const steps = d.steps.split("\n").map((s) => s.trim()).filter(Boolean);
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave(d); }} className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <input aria-label="Routine name" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="e.g. Morning reset" className={cn(inputCls, "min-w-0 flex-1")} />
        <select aria-label="Time of day" value={d.time_of_day} onChange={(e) => setD({ ...d, time_of_day: e.target.value as Draft["time_of_day"] })} className={inputCls}><option value="morning">Morning</option><option value="afternoon">Afternoon</option><option value="evening">Evening</option><option value="any">Any time</option></select>
      </div>
      <textarea aria-label="Steps, one per line" value={d.steps} onChange={(e) => setD({ ...d, steps: e.target.value })} rows={3} placeholder={"One step per line\nGlass of water\n10 min stretch"} className={cn(inputCls, "h-auto w-full py-1.5")} />
      <div className="flex flex-wrap gap-1" role="group" aria-label="Days">
        {WEEKDAYS.map((w, i) => {
          const on = d.weekdays.includes(i);
          return <button type="button" key={w} aria-pressed={on} onClick={() => setD({ ...d, weekdays: on ? d.weekdays.filter((x) => x !== i) : [...d.weekdays, i] })} className={cn("rounded-md border px-2 py-1 text-xs", on ? "border-accent/50 bg-accent/15" : "border-border text-muted")}>{w}</button>;
        })}
        <span className="self-center pl-1 text-xs text-muted">{weekdaysLabel(d.weekdays)}</span>
      </div>
      <div className="flex gap-2">
        <Button type="submit" className="h-9" loading={saving} disabled={!d.name.trim() || !steps.length}>Save routine</Button>
        {onCancel && <Button type="button" variant="ghost" className="h-9" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}

function payload(d: Draft, active = true) {
  return { name: d.name.trim(), time_of_day: d.time_of_day, steps: d.steps.split("\n").map((s) => s.trim()).filter(Boolean), weekdays: d.weekdays, active };
}

function RoutineCard({ r, today }: { r: Routine; today: string }) {
  const refresh = useRefreshPersonal("routines");
  const [editing, setEditing] = useState(false);
  const tick = useMutation({ mutationFn: (done: number[]) => api(`/routines/${r.id}/log`, { method: "PUT", body: { day: today, done_steps: done } }), onSuccess: refresh });
  const save = useMutation({ mutationFn: (d: Draft) => api(`/routines/${r.id}`, { method: "PUT", body: payload(d, r.active) }), onSuccess: () => { setEditing(false); refresh(); } });
  const toggle = useMutation({ mutationFn: () => api(`/routines/${r.id}`, { method: "PUT", body: { ...payload({ name: r.name, time_of_day: r.time_of_day, steps: r.steps.join("\n"), weekdays: r.weekdays }), active: !r.active } }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api(`/routines/${r.id}`, { method: "DELETE" }), onSuccess: refresh });
  const done = new Set(r.done_steps);
  if (editing) return <Card><Editor start={{ name: r.name, time_of_day: r.time_of_day, steps: r.steps.join("\n"), weekdays: r.weekdays }} onSave={(d) => save.mutate(d)} saving={save.isPending} onCancel={() => setEditing(false)} /></Card>;
  return (
    <Card className={cn(!r.active && "opacity-60")}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <CardTitle>{r.name}</CardTitle>
          <p className="text-xs text-muted"><span className="capitalize">{r.time_of_day === "any" ? "Any time" : r.time_of_day}</span> · {weekdaysLabel(r.weekdays)} · done fully on {r.completed_days} of the last {r.due_days} days it was due</p>
        </div>
        <button onClick={() => setEditing(true)} className="rounded p-1.5 text-muted hover:bg-raised" aria-label={`Edit ${r.name}`}><Pencil className="size-3.5" /></button>
        <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${r.name}`}><Trash2 className="size-3.5" /></button>
      </div>
      {r.due_today ? (
        <ul className="mt-3 space-y-1.5">
          {r.steps.map((s, i) => {
            const on = done.has(i);
            return (
              <li key={i}>
                <button onClick={() => tick.mutate(on ? r.done_steps.filter((x) => x !== i) : [...r.done_steps, i])} aria-pressed={on} className="flex w-full items-center gap-2 text-left text-sm">
                  <span className={cn("flex size-5 shrink-0 items-center justify-center rounded border", on ? "border-good/50 bg-good/20 text-good" : "border-border")}>{on && <Check className="size-3" />}</span>
                  <span className={cn(on && "text-muted line-through")}>{s}</span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : <p className="mt-3 text-sm text-muted">{r.active ? "Not due today." : "Paused."}</p>}
      {r.due_today && done.size === r.steps.length && <p className="mt-2 text-xs text-good">All done for today.</p>}
      <Button variant="ghost" className="mt-2 h-7 px-2 text-xs" onClick={() => toggle.mutate()}>{r.active ? "Pause" : "Resume"}</Button>
      {(tick.isError || toggle.isError) && <Alert>{errorText(tick.error ?? toggle.error)}</Alert>}
    </Card>
  );
}

export function Routines({ today }: { today: string }) {
  const refresh = useRefreshPersonal("routines");
  const q = useQuery({ queryKey: ["personal", "routines", today], queryFn: () => api<{ day: string; routines: Routine[] }>(`/routines?day=${today}`) });
  const [key, setKey] = useState(0);
  const add = useMutation({ mutationFn: (d: Draft) => api("/routines", { method: "POST", body: payload(d) }), onSuccess: () => { setKey((k) => k + 1); refresh(); } });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <div className="space-y-3">
        {q.isLoading ? <Skeleton className="h-40" /> : q.isError ? <Alert>Couldn&apos;t load routines.</Alert> : !q.data?.routines.length ? <Empty>No routines yet. Make one with the steps you want to tick off.</Empty> : (
          q.data.routines.map((r) => <RoutineCard key={r.id} r={r} today={today} />)
        )}
      </div>
      <Card className="h-fit">
        <CardTitle>New routine</CardTitle>
        <div className="mt-3"><Editor key={key} start={EMPTY} onSave={(d) => add.mutate(d)} saving={add.isPending} /></div>
        {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      </Card>
    </div>
  );
}
