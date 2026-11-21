"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Recurring, dueLabel, money } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { useMeta, useRefreshFinance } from "./hooks";

const CATEGORY_FOR: Partial<Record<Recurring["kind"], string>> = { emi: "EMI", rent: "Rent", bill: "Bills", subscription: "Entertainment" };
const KIND: Record<Recurring["kind"], string> = { emi: "EMI", bill: "Bill", subscription: "Subscription", rent: "Rent", other: "Other" };

function AddBill({ today, onDone }: { today: string; onDone: () => void }) {
  const meta = useMeta();
  const refresh = useRefreshFinance();
  const [f, setF] = useState({ name: "", kind: "bill" as Recurring["kind"], amount: "", category: "Bills", day_of_month: "5", starts_on: today, remaining: "", remind_days: "2" });
  const set = (p: Partial<typeof f>) => setF((x) => ({ ...x, ...p }));
  const add = useMutation({
    mutationFn: () =>
      api("/finance/recurring", {
        method: "POST",
        body: { ...f, name: f.name.trim(), day_of_month: Number(f.day_of_month), remaining: f.remaining ? Number(f.remaining) : null, remind_days: Number(f.remind_days) },
      }),
    onSuccess: () => { refresh(); onDone(); },
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="mt-3 space-y-3 rounded-lg border border-border bg-raised/40 p-3">
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-sm sm:col-span-2">Name<input required maxLength={80} value={f.name} onChange={(e) => set({ name: e.target.value })} placeholder="Car loan EMI, Airtel, Rent" className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Type
          <select aria-label="Type" value={f.kind} onChange={(e) => { const kind = e.target.value as Recurring["kind"]; set({ kind, category: CATEGORY_FOR[kind] ?? f.category }); }} className={cn(inputCls, "mt-1 w-full")}>
            {Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="text-sm">Amount (₹)<input required type="number" min="1" step="0.01" value={f.amount} onChange={(e) => set({ amount: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Due on day<input required type="number" min="1" max="31" value={f.day_of_month} onChange={(e) => set({ day_of_month: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Category
          <select aria-label="Category" value={f.category} onChange={(e) => set({ category: e.target.value })} className={cn(inputCls, "mt-1 w-full")}>
            {meta.data?.expense_categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="text-sm">First due from<input required type="date" value={f.starts_on} onChange={(e) => set({ starts_on: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Payments left<input type="number" min="0" max="600" value={f.remaining} onChange={(e) => set({ remaining: e.target.value })} placeholder="Ongoing" className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Remind days before<input type="number" min="0" max="14" value={f.remind_days} onChange={(e) => set({ remind_days: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
      </div>
      {add.isError && <Alert>{errorText(add.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" className="h-9" loading={add.isPending}>Add</Button>
        <Button type="button" variant="ghost" className="h-9" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

function BillRow({ p }: { p: Recurring }) {
  const refresh = useRefreshFinance();
  const paid = useMutation({ mutationFn: () => api(`/finance/recurring/${p.id}/paid`, { method: "POST", body: {} }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api(`/finance/recurring/${p.id}`, { method: "DELETE" }), onSuccess: refresh });
  const overdue = (p.days_left ?? 1) < 0;
  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{p.name} <span className="ml-1 text-xs font-normal text-muted">{KIND[p.kind]}</span></p>
        <p className={cn("text-xs", overdue ? "text-danger" : "text-muted")}>
          {p.active ? `${dueLabel(p.days_left)}${p.next_due ? ` · ${dayLabel(p.next_due)}` : ""}` : "Finished"}
          {p.remaining !== null && p.active && ` · ${p.remaining} left`}
          {p.last_paid_on && ` · last paid ${dayLabel(p.last_paid_on, { day: "numeric", month: "short" })}`}
        </p>
      </div>
      <span className="text-sm tabular-nums">{money(p.amount)}</span>
      {p.active && <Button variant="secondary" className="h-8 px-3" loading={paid.isPending} onClick={() => paid.mutate()}><Check className="size-3.5" />Mark paid</Button>}
      <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${p.name}`}><Trash2 className="size-3.5" /></button>
      {(paid.isError || remove.isError) && <div className="w-full"><Alert>{errorText(paid.error ?? remove.error)}</Alert></div>}
    </li>
  );
}

export function Bills({ today }: { today: string }) {
  const q = useQuery({ queryKey: ["finance", "recurring"], queryFn: () => api<Recurring[]>("/finance/recurring") });
  const [adding, setAdding] = useState(false);
  const monthly = (q.data ?? []).filter((p) => p.active).reduce((n, p) => n + Number(p.amount), 0);
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle>EMIs, bills and subscriptions</CardTitle>
          <p className="mt-1 text-sm text-muted">You get a reminder before each one is due. Marking it paid records the spending. NEXUS never pays anything.</p>
        </div>
        {!adding && <Button variant="secondary" className="h-9" onClick={() => setAdding(true)}><Plus className="size-4" />Add</Button>}
      </div>
      {adding && <AddBill today={today} onDone={() => setAdding(false)} />}
      {q.isLoading ? <Skeleton className="mt-4 h-32" /> : q.isError ? <div className="mt-4"><Alert>Couldn&apos;t load payments.</Alert></div> : !q.data?.length ? (
        <div className="mt-4"><Empty>No recurring payments yet. Add your EMIs, rent and bills to get reminders.</Empty></div>
      ) : (
        <>
          <p className="mt-4 text-sm text-muted">About {money(monthly)} a month while active.</p>
          <ul className="divide-y divide-border">{q.data.map((p) => <BillRow key={p.id} p={p} />)}</ul>
        </>
      )}
    </Card>
  );
}
