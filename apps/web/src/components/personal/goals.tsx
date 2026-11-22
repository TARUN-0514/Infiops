"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { AREAS, type Goal, type Milestone, goalProgress } from "@/lib/personal";
import { cn } from "@/lib/utils";
import { useRefreshPersonal } from "./hooks";

type Draft = Pick<Goal, "title" | "area" | "why" | "target_date" | "status" | "progress" | "milestones">;

function body(g: Draft) {
  return { title: g.title.trim(), area: g.area, why: g.why || null, target_date: g.target_date || null, status: g.status, progress: g.progress, milestones: g.milestones };
}

function GoalCard({ g }: { g: Goal }) {
  const refresh = useRefreshPersonal("goals");
  const [step, setStep] = useState("");
  const save = useMutation({ mutationFn: (d: Draft) => api(`/goals/${g.id}`, { method: "PUT", body: body(d) }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api(`/goals/${g.id}`, { method: "DELETE" }), onSuccess: refresh });
  const setMs = (milestones: Milestone[]) => save.mutate({ ...g, milestones });
  const pct = goalProgress(g.milestones, g.progress);
  return (
    <li className={cn("rounded-xl border border-border bg-surface/80 p-4", g.status !== "active" && "opacity-70")}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{g.title}</p>
          <p className="text-xs capitalize text-muted">{[g.area, g.target_date ? `by ${dayLabel(g.target_date, { day: "numeric", month: "short", year: "numeric" })}` : null, g.days_left !== null && g.status === "active" ? (g.days_left >= 0 ? `${g.days_left} days left` : "past target") : null].filter(Boolean).join(" · ")}</p>
        </div>
        <select aria-label={`${g.title} status`} value={g.status} onChange={(e) => save.mutate({ ...g, status: e.target.value as Goal["status"] })} className={cn(inputCls, "h-7 text-xs")}>
          <option value="active">Active</option><option value="done">Done</option><option value="dropped">Dropped</option>
        </select>
        <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${g.title}`}><Trash2 className="size-3.5" /></button>
      </div>
      {g.why && <p className="mt-2 text-sm text-muted">{g.why}</p>}
      <div className="mt-3 flex items-center gap-2"><Bar pct={pct} tone={pct >= 100 ? "good" : "accent"} /><span className="w-10 text-right text-xs tabular-nums">{pct}%</span></div>
      {!g.milestones.length && g.status === "active" && (
        <input aria-label={`${g.title} progress`} type="range" min={0} max={100} step={5} defaultValue={g.progress} onPointerUp={(e) => save.mutate({ ...g, progress: Number(e.currentTarget.value) })} onKeyUp={(e) => save.mutate({ ...g, progress: Number(e.currentTarget.value) })} className="mt-2 w-full accent-[rgb(var(--accent))]" />
      )}
      <ul className="mt-3 space-y-1">
        {g.milestones.map((m, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            <button onClick={() => setMs(g.milestones.map((x, j) => (j === i ? { ...x, done: !x.done } : x)))} aria-pressed={m.done} aria-label={`${m.title} done`} className={cn("flex size-5 items-center justify-center rounded border", m.done ? "border-good/50 bg-good/20 text-good" : "border-border")}>{m.done && <Check className="size-3" />}</button>
            <span className={cn("flex-1", m.done && "text-muted line-through")}>{m.title}</span>
            <button onClick={() => setMs(g.milestones.filter((_, j) => j !== i))} className="text-muted hover:text-danger" aria-label={`Remove ${m.title}`}><Trash2 className="size-3" /></button>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => { e.preventDefault(); if (step.trim()) { setMs([...g.milestones, { title: step.trim(), done: false }]); setStep(""); } }} className="mt-2">
        <input aria-label={`Add a milestone to ${g.title}`} value={step} onChange={(e) => setStep(e.target.value)} placeholder="+ Milestone" className={cn(inputCls, "h-8 w-full bg-transparent")} />
      </form>
      {save.isError && <div className="mt-2"><Alert>{errorText(save.error)}</Alert></div>}
    </li>
  );
}

export function Goals() {
  const refresh = useRefreshPersonal("goals");
  const q = useQuery({ queryKey: ["personal", "goals"], queryFn: () => api<Goal[]>("/goals") });
  const [d, setD] = useState<Draft>({ title: "", area: "personal", why: "", target_date: "", status: "active", progress: 0, milestones: [] });
  const add = useMutation({ mutationFn: () => api("/goals", { method: "POST", body: body(d) }), onSuccess: () => { setD({ ...d, title: "", why: "", target_date: "" }); refresh(); } });
  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>New goal</CardTitle>
        <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="mt-3 grid gap-2 sm:grid-cols-4">
          <input aria-label="Goal" value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })} placeholder="e.g. Pass OSCP" className={cn(inputCls, "sm:col-span-2")} />
          <select aria-label="Area" value={d.area} onChange={(e) => setD({ ...d, area: e.target.value })} className={cn(inputCls, "capitalize")}>{AREAS.map((a) => <option key={a} value={a}>{a}</option>)}</select>
          <input aria-label="Target date" type="date" value={d.target_date ?? ""} onChange={(e) => setD({ ...d, target_date: e.target.value })} className={inputCls} />
          <input aria-label="Why it matters" value={d.why ?? ""} onChange={(e) => setD({ ...d, why: e.target.value })} placeholder="Why it matters (optional)" className={cn(inputCls, "sm:col-span-3")} />
          <Button type="submit" className="h-9" loading={add.isPending} disabled={!d.title.trim()}><Plus className="size-4" aria-hidden />Add goal</Button>
        </form>
        {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      </Card>
      {q.isLoading ? <Skeleton className="h-32" /> : q.isError ? <Alert>Couldn&apos;t load goals.</Alert> : !q.data?.length ? <Empty>No goals yet. Add one, then break it into milestones.</Empty> : (
        <ul className="grid gap-3 md:grid-cols-2">{q.data.map((g) => <GoalCard key={g.id} g={g} />)}</ul>
      )}
    </div>
  );
}
