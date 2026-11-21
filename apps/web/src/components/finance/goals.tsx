"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Goal, money } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { useRefreshFinance } from "./hooks";

function AddGoal({ onDone }: { onDone: () => void }) {
  const refresh = useRefreshFinance();
  const [f, setF] = useState({ name: "", target: "", saved: "", target_date: "" });
  const add = useMutation({
    mutationFn: () => api("/finance/goals", { method: "POST", body: { name: f.name.trim(), target: f.target, saved: f.saved || "0", target_date: f.target_date || null } }),
    onSuccess: () => { refresh(); onDone(); },
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="mt-3 space-y-3 rounded-lg border border-border bg-raised/40 p-3">
      <div className="grid gap-2 sm:grid-cols-4">
        <label className="text-sm">Goal<input required maxLength={80} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Emergency fund" className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Target (₹)<input required type="number" min="1" step="0.01" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Saved so far (₹)<input type="number" min="0" step="0.01" value={f.saved} onChange={(e) => setF({ ...f, saved: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">By (optional)<input type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
      </div>
      {add.isError && <Alert>{errorText(add.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" className="h-9" loading={add.isPending}>Add goal</Button>
        <Button type="button" variant="ghost" className="h-9" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

function GoalRow({ g }: { g: Goal }) {
  const refresh = useRefreshFinance();
  const [amount, setAmount] = useState("");
  const update = useMutation({
    mutationFn: () => api(`/finance/goals/${g.id}`, { method: "PATCH", body: { name: g.name, target: g.target, target_date: g.target_date, saved: String(Math.max(0, Number(g.saved) + Number(amount))) } }),
    onSuccess: () => { setAmount(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: () => api(`/finance/goals/${g.id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <li className="py-3">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{g.name}</span>
        <span className="tabular-nums">{money(g.saved)} <span className="text-muted">of {money(g.target)}</span></span>
      </div>
      <div className="mt-1.5"><Bar pct={g.percent} tone={g.percent >= 100 ? "good" : "accent"} /></div>
      <p className="mt-1 text-xs text-muted">
        {g.percent >= 100 ? "Reached." : `${g.percent}% · ${money(g.left)} to go`}
        {g.target_date && g.percent < 100 && ` · by ${dayLabel(g.target_date, { day: "numeric", month: "short", year: "numeric" })}`}
        {g.monthly_needed && g.percent < 100 && ` · about ${money(g.monthly_needed)} a month`}
      </p>
      <form onSubmit={(e) => { e.preventDefault(); if (Number(amount)) update.mutate(); }} className="mt-2 flex items-center gap-2">
        <label className="sr-only" htmlFor={`add-${g.id}`}>Amount to add to {g.name}</label>
        <input id={`add-${g.id}`} type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Add or withdraw ₹" className={cn(inputCls, "w-40")} />
        <Button type="submit" variant="secondary" className="h-9" loading={update.isPending} disabled={!Number(amount)}>Update</Button>
        <button type="button" onClick={() => remove.mutate()} className="ml-auto rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${g.name}`}><Trash2 className="size-3.5" /></button>
      </form>
      {update.isError && <div className="mt-2"><Alert>{errorText(update.error)}</Alert></div>}
    </li>
  );
}

export function Goals() {
  const q = useQuery({ queryKey: ["finance", "goals"], queryFn: () => api<Goal[]>("/finance/goals") });
  const [adding, setAdding] = useState(false);
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle>Savings goals</CardTitle>
          <p className="mt-1 text-sm text-muted">Track what you&apos;ve put aside. Use a negative amount to record a withdrawal.</p>
        </div>
        {!adding && <Button variant="secondary" className="h-9" onClick={() => setAdding(true)}><Plus className="size-4" />Add goal</Button>}
      </div>
      {adding && <AddGoal onDone={() => setAdding(false)} />}
      {q.isLoading ? <Skeleton className="mt-4 h-24" /> : q.isError ? <div className="mt-4"><Alert>Couldn&apos;t load goals.</Alert></div> : !q.data?.length ? (
        <div className="mt-4"><Empty>No savings goals yet.</Empty></div>
      ) : (
        <ul className="divide-y divide-border">{q.data.map((g) => <GoalRow key={g.id} g={g} />)}</ul>
      )}
    </Card>
  );
}
