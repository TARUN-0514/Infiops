"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Copy, Pencil, Plus, Trash2, Trophy, X } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Best, type SetDraft, type Workout, emptySet, num, summarise, toSets, volume } from "@/lib/fitness";
import { cn } from "@/lib/utils";
import { useLibrary, useRefreshFitness } from "./hooks";

function draftsFrom(w: Workout): SetDraft[] {
  return w.sets.map((s) => ({
    exercise: s.exercise,
    reps: s.reps ? String(s.reps) : "",
    weight_kg: s.weight_kg ? String(Number(s.weight_kg)) : "",
    seconds: s.seconds ? String(Math.round(s.seconds / 60)) : "",
    distance_km: s.distance_km ? String(Number(s.distance_km)) : "",
  }));
}

function Logger({ today, initial, onDone }: { today: string; initial?: Workout; onDone?: () => void }) {
  const lib = useLibrary();
  const refresh = useRefreshFitness();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [day, setDay] = useState(initial?.day ?? today);
  const [minutes, setMinutes] = useState(initial?.minutes ? String(initial.minutes) : "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [rows, setRows] = useState<SetDraft[]>(initial ? draftsFrom(initial) : [emptySet()]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const update = (i: number, patch: Partial<SetDraft>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const parsed = toSets(rows);
  const save = useMutation({
    mutationFn: () => {
      const body = { day, title: title.trim() || "Workout", minutes: minutes ? Number(minutes) : null, notes: notes.trim() || null, sets: parsed.sets };
      return initial ? api(`/fitness/workouts/${initial.id}`, { method: "PUT", body }) : api("/fitness/workouts", { method: "POST", body });
    },
    onSuccess: () => {
      refresh();
      setError(null);
      if (initial) return onDone?.();
      setRows([emptySet()]);
      setTitle("");
      setMinutes("");
      setNotes("");
      setDone(true);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setDone(false);
        if (parsed.error) return setError(parsed.error);
        save.mutate();
      }}
      className="space-y-3"
    >
      <div className="grid gap-2 sm:grid-cols-4">
        <label className="text-sm sm:col-span-2">Workout<input maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Push day, Legs, 5k run" className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Date<input type="date" required max={today} value={day} onChange={(e) => setDay(e.target.value)} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Minutes<input type="number" min="1" max="1440" value={minutes} onChange={(e) => setMinutes(e.target.value)} className={cn(inputCls, "mt-1 w-full")} /></label>
      </div>
      <datalist id="exercise-list">{lib.data?.map((x) => <option key={x.name} value={x.name}>{x.muscle}</option>)}</datalist>
      <div className="space-y-2">
        <div className="hidden grid-cols-[1fr_5rem_5rem_5rem_5rem_2rem] gap-2 px-1 text-xs text-muted sm:grid">
          <span>Exercise</span><span>Reps</span><span>kg</span><span>Minutes</span><span>km</span><span />
        </div>
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-4 gap-2 rounded-lg border border-border p-2 sm:grid-cols-[1fr_5rem_5rem_5rem_5rem_2rem] sm:border-0 sm:p-0">
            <input list="exercise-list" aria-label={`Set ${i + 1} exercise`} value={r.exercise} onChange={(e) => update(i, { exercise: e.target.value })} placeholder="Exercise" className={cn(inputCls, "col-span-3 sm:col-span-1")} />
            <button type="button" onClick={() => setRows((x) => (x.length > 1 ? x.filter((_, j) => j !== i) : [emptySet()]))} className="justify-self-end rounded p-1.5 text-muted hover:bg-raised hover:text-danger sm:order-last" aria-label={`Remove set ${i + 1}`}><X className="size-4" /></button>
            <input type="number" min="0" max="1000" aria-label={`Set ${i + 1} reps`} value={r.reps} onChange={(e) => update(i, { reps: e.target.value })} placeholder="Reps" className={inputCls} />
            <input type="number" min="0" max="1000" step="0.25" aria-label={`Set ${i + 1} weight in kg`} value={r.weight_kg} onChange={(e) => update(i, { weight_kg: e.target.value })} placeholder="kg" className={inputCls} />
            <input type="number" min="0" max="1440" aria-label={`Set ${i + 1} minutes`} value={r.seconds} onChange={(e) => update(i, { seconds: e.target.value })} placeholder="min" className={inputCls} />
            <input type="number" min="0" max="1000" step="0.01" aria-label={`Set ${i + 1} distance in km`} value={r.distance_km} onChange={(e) => update(i, { distance_km: e.target.value })} placeholder="km" className={inputCls} />
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="ghost" className="h-8 px-2" onClick={() => setRows((x) => [...x, emptySet()])}><Plus className="size-4" />Set</Button>
          <Button type="button" variant="ghost" className="h-8 px-2" onClick={() => setRows((x) => [...x, { ...x[x.length - 1] }])}><Copy className="size-4" />Repeat last set</Button>
        </div>
      </div>
      <label className="block text-sm">Notes (optional)<input maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} className={cn(inputCls, "mt-1 w-full")} /></label>
      {error && <Alert>{error}</Alert>}
      {done && <p className="text-sm text-good" role="status">Workout saved.</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" className="h-9" loading={save.isPending}>{initial ? "Save changes" : "Save workout"}</Button>
        {initial && <Button type="button" variant="ghost" className="h-9" onClick={onDone}>Cancel</Button>}
        {!parsed.error && <span className="text-sm text-muted">{parsed.sets.length} sets · {num(volume(parsed.sets), 0)} kg moved</span>}
      </div>
    </form>
  );
}

function WorkoutCard({ w, today }: { w: Workout; today: string }) {
  const refresh = useRefreshFitness();
  const [editing, setEditing] = useState(false);
  const remove = useMutation({ mutationFn: () => api(`/fitness/workouts/${w.id}`, { method: "DELETE" }), onSuccess: refresh });
  if (editing) return <li className="py-3"><Logger today={today} initial={w} onDone={() => setEditing(false)} /></li>;
  return (
    <li className="group py-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{w.title}</p>
          <p className="text-xs text-muted">{[dayLabel(w.day, { weekday: "short", day: "numeric", month: "short" }), w.minutes ? `${w.minutes} min` : null, Number(w.volume_kg) ? `${num(w.volume_kg, 0)} kg moved` : null].filter(Boolean).join(" · ")}</p>
        </div>
        <div className="flex opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
          <button onClick={() => setEditing(true)} className="rounded p-1.5 text-muted hover:bg-raised" aria-label={`Edit ${w.title}`}><Pencil className="size-3.5" /></button>
          <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${w.title}`}><Trash2 className="size-3.5" /></button>
        </div>
      </div>
      <ul className="mt-1.5 space-y-0.5 text-sm">
        {summarise(w.sets).map((s) => <li key={s.exercise}><span className="text-muted">{s.exercise}:</span> {s.text}</li>)}
      </ul>
      {w.notes && <p className="mt-1 text-xs text-muted">{w.notes}</p>}
    </li>
  );
}

function Bests() {
  const q = useQuery({ queryKey: ["fitness", "bests"], queryFn: () => api<Record<string, Best>>("/fitness/bests") });
  const rows = Object.entries(q.data ?? {}).sort((a, b) => a[0].localeCompare(b[0]));
  return (
    <Card>
      <CardTitle className="flex items-center gap-2"><Trophy className="size-4 text-warn" />Heaviest sets</CardTitle>
      {q.isLoading ? <Skeleton className="mt-3 h-20" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load records.</Alert></div> : !rows.length ? (
        <p className="mt-3 text-sm text-muted">Log a weighted set to see your records.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border text-sm">
          {rows.map(([name, b]) => (
            <li key={name} className="flex justify-between gap-2 py-1.5">
              <span className="truncate">{name}</span>
              <span className="whitespace-nowrap tabular-nums">{num(b.weight_kg)} kg{b.reps ? ` × ${b.reps}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function CustomExercise() {
  const refresh = useRefreshFitness();
  const [name, setName] = useState("");
  const [muscle, setMuscle] = useState("Other");
  const add = useMutation({ mutationFn: () => api("/fitness/exercises", { method: "POST", body: { name: name.trim(), muscle } }), onSuccess: () => { setName(""); refresh(); } });
  return (
    <Card>
      <CardTitle>Your exercises</CardTitle>
      <p className="mt-1 text-xs text-muted">The list has common gym and cardio exercises. Add your own here.</p>
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim().length >= 2) add.mutate(); }} className="mt-3 flex flex-wrap gap-2">
        <label htmlFor="ex-name" className="sr-only">Exercise name</label>
        <input id="ex-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Exercise name" className={cn(inputCls, "min-w-0 flex-1")} />
        <label htmlFor="ex-muscle" className="sr-only">Muscle group</label>
        <select id="ex-muscle" value={muscle} onChange={(e) => setMuscle(e.target.value)} className={inputCls}>
          {["Chest", "Back", "Legs", "Shoulders", "Arms", "Core", "Cardio", "Other"].map((m) => <option key={m}>{m}</option>)}
        </select>
        <Button type="submit" variant="secondary" className="h-9" loading={add.isPending} disabled={name.trim().length < 2}>Add</Button>
      </form>
      {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      {add.isSuccess && <p className="mt-2 text-sm text-good" role="status">Added to your list.</p>}
    </Card>
  );
}

export function Workouts({ today }: { today: string }) {
  const q = useQuery({ queryKey: ["fitness", "workouts"], queryFn: () => api<Workout[]>("/fitness/workouts") });
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card>
          <CardTitle>Log a workout</CardTitle>
          <div className="mt-4"><Logger today={today} /></div>
        </Card>
        <Card>
          <CardTitle>Last 60 days</CardTitle>
          {q.isLoading ? <Skeleton className="mt-4 h-32" /> : q.isError ? <div className="mt-4"><Alert>Couldn&apos;t load workouts.</Alert></div> : !q.data?.length ? (
            <div className="mt-4"><Empty>No workouts logged yet. Log one above, or tell NEXUS in chat: &quot;did 3 sets of 8 bench at 60 kg&quot;.</Empty></div>
          ) : (
            <ul className="divide-y divide-border">{q.data.map((w) => <WorkoutCard key={w.id} w={w} today={today} />)}</ul>
          )}
        </Card>
      </div>
      <div className="space-y-4">
        <Bests />
        <CustomExercise />
      </div>
    </div>
  );
}
