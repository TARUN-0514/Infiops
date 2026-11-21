"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type Debt, type PayoffPlan, money, payoffLabel } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { useRefreshFinance } from "./hooks";

function AddDebt({ onDone }: { onDone: () => void }) {
  const refresh = useRefreshFinance();
  const [f, setF] = useState({ name: "", balance: "", annual_rate: "", min_payment: "" });
  const add = useMutation({ mutationFn: () => api("/finance/debts", { method: "POST", body: { ...f, name: f.name.trim() } }), onSuccess: () => { refresh(); onDone(); } });
  const field = (k: keyof typeof f, label: string, extra: React.InputHTMLAttributes<HTMLInputElement>) => (
    <label className="text-sm">{label}<input required value={f[k]} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} className={cn(inputCls, "mt-1 w-full")} {...extra} /></label>
  );
  return (
    <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="mt-3 space-y-3 rounded-lg border border-border bg-raised/40 p-3">
      <div className="grid gap-2 sm:grid-cols-4">
        {field("name", "Name", { maxLength: 80, placeholder: "Credit card" })}
        {field("balance", "Owed (₹)", { type: "number", min: 0, step: "0.01" })}
        {field("annual_rate", "Interest % a year", { type: "number", min: 0, max: 100, step: "0.01" })}
        {field("min_payment", "Minimum a month (₹)", { type: "number", min: 1, step: "0.01" })}
      </div>
      {add.isError && <Alert>{errorText(add.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" className="h-9" loading={add.isPending}>Add</Button>
        <Button type="button" variant="ghost" className="h-9" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

function PlanCard({ title, hint, plan, best }: { title: string; hint: string; plan: PayoffPlan; best: boolean }) {
  return (
    <div className={cn("rounded-lg border p-3", best ? "border-good/40 bg-good/5" : "border-border")}>
      <p className="text-sm font-medium">{title} {best && <span className="ml-1 text-xs text-good">less interest</span>}</p>
      <p className="text-xs text-muted">{hint}</p>
      {plan.feasible ? (
        <>
          <p className="mt-2 text-lg font-semibold">{payoffLabel(plan.months)}</p>
          <p className="text-sm text-muted">{money(plan.total_interest)} interest</p>
          <ol className="mt-2 space-y-0.5 text-xs text-muted">
            {plan.order.map((o, i) => <li key={o.id}>{i + 1}. {o.name}, paid off in month {o.paid_off_month}</li>)}
          </ol>
        </>
      ) : (
        <p className="mt-2 text-sm text-danger">{plan.reason}</p>
      )}
    </div>
  );
}

export function Debts() {
  const refresh = useRefreshFinance();
  const [adding, setAdding] = useState(false);
  const [extra, setExtra] = useState("0");
  const debts = useQuery({ queryKey: ["finance", "debts"], queryFn: () => api<Debt[]>("/finance/debts") });
  const plan = useQuery({
    queryKey: ["finance", "plan", extra],
    queryFn: () => api<{ avalanche: PayoffPlan; snowball: PayoffPlan }>(`/finance/debts/plan?extra=${Number(extra) || 0}`),
    enabled: (debts.data?.length ?? 0) > 0,
  });
  const remove = useMutation({ mutationFn: (id: string) => api(`/finance/debts/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const total = (debts.data ?? []).reduce((n, d) => n + Number(d.balance), 0);
  const a = plan.data?.avalanche;
  const s = plan.data?.snowball;
  const avalancheBest = !!a && !!s && a.feasible && Number(a.total_interest) < Number(s.total_interest ?? Infinity);
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>Debts</CardTitle>
            <p className="mt-1 text-sm text-muted">Loans and card balances you&apos;re paying down. Update the balance when you get a statement.</p>
          </div>
          {!adding && <Button variant="secondary" className="h-9" onClick={() => setAdding(true)}><Plus className="size-4" />Add debt</Button>}
        </div>
        {adding && <AddDebt onDone={() => setAdding(false)} />}
        {debts.isLoading ? <Skeleton className="mt-4 h-24" /> : debts.isError ? <div className="mt-4"><Alert>Couldn&apos;t load debts.</Alert></div> : !debts.data?.length ? (
          <div className="mt-4"><Empty>No debts recorded.</Empty></div>
        ) : (
          <>
            <p className="mt-4 text-sm">{money(total)} owed in total.</p>
            <ul className="divide-y divide-border">
              {debts.data.map((d) => (
                <li key={d.id} className="flex items-center gap-3 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">{d.name}</span>
                  <span className="text-xs text-muted">{Number(d.annual_rate)}% · min {money(d.min_payment)}</span>
                  <span className="tabular-nums">{money(d.balance)}</span>
                  <button onClick={() => remove.mutate(d.id)} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${d.name}`}><Trash2 className="size-3.5" /></button>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
      {(debts.data?.length ?? 0) > 0 && (
        <Card>
          <CardTitle>Payoff plan</CardTitle>
          <label className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            Extra you can pay each month (₹)
            <input type="number" min="0" step="500" value={extra} onChange={(e) => setExtra(e.target.value)} className={cn(inputCls, "w-32")} />
          </label>
          {plan.isLoading ? <Skeleton className="mt-4 h-32" /> : plan.isError ? <div className="mt-4"><Alert>{errorText(plan.error)}</Alert></div> : a && s ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <PlanCard title="Avalanche" hint="Highest interest first" plan={a} best={avalancheBest} />
              <PlanCard title="Snowball" hint="Smallest balance first" plan={s} best={false} />
            </div>
          ) : null}
          <p className="mt-3 text-xs text-muted">An estimate from your numbers, with interest added monthly. Not financial advice.</p>
        </Card>
      )}
    </div>
  );
}
