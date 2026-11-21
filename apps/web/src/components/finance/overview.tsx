"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Bar as RBar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bar, Empty, Stat, errorText, inputCls, useChartColors } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Account, type CashFlowMonth, type MonthSummary, budgetState, dueLabel, money, moneyShort, monthLabel } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { useAccounts, useRefreshFinance } from "./hooks";

function Categories({ s }: { s: MonthSummary }) {
  if (!s.categories.length) return <Empty>No spending this month yet.</Empty>;
  return (
    <ul className="space-y-3">
      {s.categories.map((c) => {
        const b = budgetState(c.spent, c.budget);
        return (
          <li key={c.category}>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
              <span>{c.category}</span>
              <span className="tabular-nums">
                {money(c.spent)}
                {c.budget && <span className="text-muted"> of {money(c.budget)}</span>}
              </span>
            </div>
            {c.budget ? (
              <>
                <Bar pct={b.pct ?? 0} tone={b.tone} />
                <p className={cn("mt-0.5 text-xs", b.tone === "danger" ? "text-danger" : "text-muted")}>
                  {Number(c.left) < 0 ? `${money(-Number(c.left))} over budget` : `${money(c.left)} left`}
                </p>
              </>
            ) : (
              <Bar pct={(Number(c.spent) / Math.max(1, Number(s.expense))) * 100} tone="accent" />
            )}
          </li>
        );
      })}
    </ul>
  );
}

function DailyChart({ s }: { s: MonthSummary }) {
  const c = useChartColors();
  const data = s.daily.map((d) => ({ day: Number(d.day.slice(8)), spent: Number(d.spent) }));
  return (
    <div className="h-48" aria-label="Spending per day">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
          <XAxis dataKey="day" tick={{ fill: c.muted, fontSize: 11 }} tickLine={false} axisLine={false} interval={4} />
          <YAxis tickFormatter={moneyShort} tick={{ fill: c.muted, fontSize: 11 }} tickLine={false} axisLine={false} width={52} />
          <Tooltip cursor={{ fill: c.border, opacity: 0.4 }} contentStyle={{ background: "rgb(var(--surface))", border: `1px solid ${c.border}`, borderRadius: 8, color: c.text }} formatter={(v) => [money(Number(v)), "Spent"]} labelFormatter={(d) => `Day ${d}`} />
          <RBar dataKey="spent" fill={c.accent} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function CashFlow() {
  const c = useChartColors();
  const q = useQuery({ queryKey: ["finance", "cashflow"], queryFn: () => api<CashFlowMonth[]>("/finance/cashflow?months=6") });
  const data = (q.data ?? []).map((m) => ({ month: monthLabel(m.month, "short"), Income: Number(m.income), Spent: Number(m.expense) }));
  const any = data.some((d) => d.Income || d.Spent);
  return (
    <Card>
      <CardTitle>Cash flow, last 6 months</CardTitle>
      {q.isLoading ? <Skeleton className="mt-4 h-56" /> : q.isError ? <div className="mt-4"><Alert>Couldn&apos;t load cash flow.</Alert></div> : !any ? (
        <div className="mt-4"><Empty>Cash flow appears once you record income and spending.</Empty></div>
      ) : (
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: c.muted, fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={moneyShort} tick={{ fill: c.muted, fontSize: 11 }} tickLine={false} axisLine={false} width={52} />
              <Tooltip cursor={{ fill: c.border, opacity: 0.4 }} contentStyle={{ background: "rgb(var(--surface))", border: `1px solid ${c.border}`, borderRadius: 8, color: c.text }} formatter={(v, name) => [money(Number(v)), String(name)]} />
              <Legend wrapperStyle={{ fontSize: 12, color: c.muted }} />
              <RBar dataKey="Income" fill={c.good} radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <RBar dataKey="Spent" fill={c.danger} radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

function AddAccount({ onDone }: { onDone: () => void }) {
  const refresh = useRefreshFinance();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Account["kind"]>("bank");
  const [opening, setOpening] = useState("");
  const add = useMutation({
    mutationFn: () => api("/finance/accounts", { method: "POST", body: { name: name.trim(), kind, opening_balance: opening || "0" } }),
    onSuccess: () => { refresh(); onDone(); },
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) add.mutate(); }} className="mt-3 space-y-2">
      <div className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="acc-name">Account name</label>
        <input id="acc-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. HDFC savings" className={cn(inputCls, "min-w-0 flex-1")} />
        <label className="sr-only" htmlFor="acc-kind">Type</label>
        <select id="acc-kind" value={kind} onChange={(e) => setKind(e.target.value as Account["kind"])} className={inputCls}>
          {(["bank", "cash", "card", "wallet", "loan"] as const).map((k) => <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>)}
        </select>
        <label className="sr-only" htmlFor="acc-open">Opening balance</label>
        <input id="acc-open" type="number" step="0.01" value={opening} onChange={(e) => setOpening(e.target.value)} placeholder="Balance today" className={cn(inputCls, "w-32")} />
        <Button type="submit" className="h-9" loading={add.isPending} disabled={!name.trim()}>Add</Button>
      </div>
      {add.isError && <Alert>{errorText(add.error)}</Alert>}
    </form>
  );
}

function Accounts() {
  const q = useAccounts();
  const [adding, setAdding] = useState(false);
  const live = (q.data ?? []).filter((a) => !a.archived);
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Accounts</CardTitle>
        <Button variant="ghost" className="h-8 px-2" onClick={() => setAdding((v) => !v)}><Plus className="size-4" />Account</Button>
      </div>
      <p className="mt-1 text-xs text-muted">Balances are worked out from what you record here, not read from your bank.</p>
      {adding && <AddAccount onDone={() => setAdding(false)} />}
      {q.isLoading ? <Skeleton className="mt-3 h-16" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load accounts.</Alert></div> : !live.length ? (
        <p className="mt-3 text-sm text-muted">No accounts yet. They&apos;re optional; add one to track a balance.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {live.map((a) => (
            <li key={a.id} className="flex items-center justify-between py-2 text-sm">
              <span>{a.name} <span className="text-xs text-muted">{a.kind}</span></span>
              <span className={cn("tabular-nums", Number(a.balance) < 0 && "text-danger")}>{money(a.balance)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Overview({ month }: { month: string }) {
  const q = useQuery({ queryKey: ["finance", "summary", month], queryFn: () => api<MonthSummary>(`/finance/summary?month=${month}`) });
  if (q.isLoading) return <div className="grid gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}</div>;
  if (q.isError || !q.data) return <Alert>Couldn&apos;t load this month. {errorText(q.error)}</Alert>;
  const s = q.data;
  const net = Number(s.net);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Spent" value={money(s.expense)} hint={`${s.count} entries`} />
        <Stat label="Income" value={money(s.income)} />
        <Stat label="Net" value={money(s.net)} tone={net < 0 ? "danger" : net > 0 ? "good" : undefined} />
        <Stat label="Days tracked" value={`${s.days_tracked} of ${s.days_elapsed}`} hint="Days with at least one entry" />
      </div>
      {s.over_budget.length > 0 && <Alert tone="warn">Over budget: {s.over_budget.join(", ")}.</Alert>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Spending per day</CardTitle>
          <div className="mt-4">{Number(s.expense) > 0 ? <DailyChart s={s} /> : <Empty>No spending recorded in {monthLabel(month)}.</Empty>}</div>
        </Card>
        <Card>
          <CardTitle>Coming up</CardTitle>
          {!s.upcoming.length ? <p className="mt-3 text-sm text-muted">No bills or EMIs due in the next two weeks.</p> : (
            <ul className="mt-3 divide-y divide-border">
              {s.upcoming.map((u) => (
                <li key={u.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate">{u.name}</p>
                    <p className={cn("text-xs", (u.days_left ?? 1) < 0 ? "text-danger" : "text-muted")}>{dueLabel(u.days_left)}{u.next_due && ` · ${dayLabel(u.next_due)}`}</p>
                  </div>
                  <span className="tabular-nums">{money(u.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>By category</CardTitle>
          <div className="mt-4"><Categories s={s} /></div>
        </Card>
        <Accounts />
      </div>
      <CashFlow />
    </div>
  );
}
