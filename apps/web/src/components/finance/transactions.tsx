"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Pencil, Search, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Tx, type TxKind, money, monthLabel, signed } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { useAccounts, useMeta, useRefreshFinance } from "./hooks";

const SOURCE: Record<Tx["source"], string> = { manual: "", voice: "By voice", chat: "From chat", csv: "Imported" };

function QuickAdd() {
  const refresh = useRefreshFinance();
  const [text, setText] = useState("");
  const [last, setLast] = useState<Tx | null>(null);
  const add = useMutation({
    mutationFn: () => api<Tx>("/finance/transactions/quick", { method: "POST", body: { text: text.trim() } }),
    onSuccess: (tx) => { setText(""); setLast(tx); refresh(); },
  });
  return (
    <Card>
      <CardTitle>Quick add</CardTitle>
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 2) add.mutate(); }} className="mt-3 flex gap-2">
        <label htmlFor="quick" className="sr-only">Quick entry</label>
        <input id="quick" value={text} onChange={(e) => setText(e.target.value)} placeholder="450 swiggy dinner · salary 85000 · 2.5k petrol" className={cn(inputCls, "h-10 min-w-0 flex-1")} />
        <Button type="submit" loading={add.isPending} disabled={text.trim().length < 2}>Add</Button>
      </form>
      <p className="mt-2 text-xs text-muted">Read on the server, no AI needed. Words like salary, refund or received make it income.</p>
      {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      {last && !add.isError && (
        <p className="mt-2 text-sm text-good" role="status">
          Added {last.kind === "income" ? "income" : "spending"} of {money(last.amount)} under {last.category}.
        </p>
      )}
    </Card>
  );
}

type Draft = { kind: TxKind; amount: string; occurred_on: string; description: string; category: string; account_id: string; to_account_id: string; notes: string };

function TxForm({ initial, onDone, today }: { initial?: Tx; onDone: () => void; today: string }) {
  const meta = useMeta();
  const accounts = useAccounts();
  const refresh = useRefreshFinance();
  const [d, setD] = useState<Draft>({
    kind: initial?.kind ?? "expense",
    amount: initial?.amount ?? "",
    occurred_on: initial?.occurred_on ?? today,
    description: initial?.description ?? "",
    category: initial?.category ?? "",
    account_id: initial?.account_id ?? "",
    to_account_id: initial?.to_account_id ?? "",
    notes: initial?.notes ?? "",
  });
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }));
  const cats = d.kind === "income" ? meta.data?.income_categories : meta.data?.expense_categories;
  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...d,
        category: d.kind === "transfer" ? null : d.category || null,
        account_id: d.account_id || null,
        to_account_id: d.kind === "transfer" ? d.to_account_id || null : null,
        notes: d.notes.trim() || null,
      };
      return initial ? api(`/finance/transactions/${initial.id}`, { method: "PATCH", body }) : api("/finance/transactions", { method: "POST", body });
    },
    onSuccess: () => { refresh(); onDone(); },
  });
  const live = (accounts.data ?? []).filter((a) => !a.archived);
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-3 rounded-lg border border-border bg-raised/40 p-3">
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Type">
        {(["expense", "income", "transfer"] as const).map((k) => (
          <button type="button" role="radio" aria-checked={d.kind === k} key={k} onClick={() => set({ kind: k, category: "" })} className={cn("rounded-lg px-3 py-1 text-sm", d.kind === k ? "bg-accent/15 text-text" : "text-muted hover:bg-raised")}>
            {k === "expense" ? "Spent" : k === "income" ? "Received" : "Transfer"}
          </button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-sm">Amount (₹)<input required type="number" min="0.01" step="0.01" value={d.amount} onChange={(e) => set({ amount: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm">Date<input required type="date" value={d.occurred_on} onChange={(e) => set({ occurred_on: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-sm sm:col-span-2">Description<input required maxLength={300} value={d.description} onChange={(e) => set({ description: e.target.value })} placeholder="What was it?" className={cn(inputCls, "mt-1 w-full")} /></label>
        {d.kind !== "transfer" && (
          <label className="text-sm">Category
            <select aria-label="Category" value={d.category} onChange={(e) => set({ category: e.target.value })} className={cn(inputCls, "mt-1 w-full")}>
              <option value="">Guess from description</option>
              {cats?.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}
        <label className="text-sm">{d.kind === "transfer" ? "From account" : "Account"}
          <select aria-label={d.kind === "transfer" ? "From account" : "Account"} value={d.account_id} onChange={(e) => set({ account_id: e.target.value })} className={cn(inputCls, "mt-1 w-full")} required={d.kind === "transfer"}>
            <option value="">{d.kind === "transfer" ? "Pick one" : "None"}</option>
            {live.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        {d.kind === "transfer" && (
          <label className="text-sm">To account
            <select aria-label="To account" required value={d.to_account_id} onChange={(e) => set({ to_account_id: e.target.value })} className={cn(inputCls, "mt-1 w-full")}>
              <option value="">Pick one</option>
              {live.filter((a) => a.id !== d.account_id).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
        )}
        <label className="text-sm sm:col-span-2">Notes (optional)<input maxLength={2000} value={d.notes} onChange={(e) => set({ notes: e.target.value })} className={cn(inputCls, "mt-1 w-full")} /></label>
      </div>
      {d.kind === "transfer" && live.length < 2 && <p className="text-xs text-muted">Add two accounts on the Overview tab to record a transfer.</p>}
      {save.isError && <Alert>{errorText(save.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" className="h-9" loading={save.isPending}>{initial ? "Save changes" : "Add entry"}</Button>
        <Button type="button" variant="ghost" className="h-9" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

function Row({ tx, today }: { tx: Tx; today: string }) {
  const refresh = useRefreshFinance();
  const [editing, setEditing] = useState(false);
  const remove = useMutation({ mutationFn: () => api(`/finance/transactions/${tx.id}`, { method: "DELETE" }), onSuccess: refresh });
  if (editing) return <li className="py-2"><TxForm initial={tx} today={today} onDone={() => setEditing(false)} /></li>;
  const s = signed(tx);
  return (
    <li className="group flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{tx.description}</p>
        <p className="text-xs text-muted">{[tx.kind === "transfer" ? "Transfer" : tx.category, SOURCE[tx.source] || null].filter(Boolean).join(" · ")}</p>
      </div>
      <span className={cn("text-sm tabular-nums", s.tone === "good" && "text-good", s.tone === "muted" && "text-muted")}>{s.text}</span>
      <div className="flex opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
        <button onClick={() => setEditing(true)} className="rounded p-1.5 text-muted hover:bg-raised" aria-label={`Edit ${tx.description}`}><Pencil className="size-3.5" /></button>
        <button onClick={() => remove.mutate()} disabled={remove.isPending} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${tx.description}`}><Trash2 className="size-3.5" /></button>
      </div>
    </li>
  );
}

export function Transactions({ month, today }: { month: string; today: string }) {
  const meta = useMeta();
  const [adding, setAdding] = useState(false);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const params = new URLSearchParams({ month });
  if (category) params.set("category", category);
  if (q) params.set("q", q);
  const list = useQuery({ queryKey: ["finance", "tx", month, category, q], queryFn: () => api<Tx[]>(`/finance/transactions?${params}`) });
  const byDay = new Map<string, Tx[]>();
  for (const t of list.data ?? []) byDay.set(t.occurred_on, [...(byDay.get(t.occurred_on) ?? []), t]);
  const cats = [...(meta.data?.expense_categories ?? []), ...(meta.data?.income_categories ?? [])];
  return (
    <div className="space-y-4">
      <QuickAdd />
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{monthLabel(month)}</CardTitle>
          {!adding && <Button variant="secondary" className="h-9" onClick={() => setAdding(true)}>Add with details</Button>}
        </div>
        {adding && <div className="mt-3"><TxForm today={today} onDone={() => setAdding(false)} /></div>}
        <div className="mt-3 flex flex-wrap gap-2">
          <form onSubmit={(e) => { e.preventDefault(); setQ(search.trim()); }} className="relative min-w-0 flex-1">
            <label htmlFor="tx-search" className="sr-only">Search descriptions</label>
            <Search className="pointer-events-none absolute left-2 top-2.5 size-4 text-muted" />
            <input id="tx-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search descriptions" className={cn(inputCls, "w-full pl-8")} />
            {q && <button type="button" onClick={() => { setQ(""); setSearch(""); }} className="absolute right-2 top-2.5 text-muted" aria-label="Clear search"><X className="size-4" /></button>}
          </form>
          <label htmlFor="tx-cat" className="sr-only">Filter by category</label>
          <select id="tx-cat" value={category} onChange={(e) => setCategory(e.target.value)} className={inputCls}>
            <option value="">All categories</option>
            {[...new Set(cats)].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {list.isLoading ? <Skeleton className="mt-4 h-40" /> : list.isError ? <div className="mt-4"><Alert>Couldn&apos;t load entries. {errorText(list.error)}</Alert></div> : !byDay.size ? (
          <div className="mt-4"><Empty>{q || category ? "Nothing matches." : `Nothing recorded in ${monthLabel(month)}. Use quick add, or import a bank statement.`}</Empty></div>
        ) : (
          <div className="mt-4 space-y-4">
            {[...byDay.entries()].map(([day, rows]) => {
              const spent = rows.filter((r) => r.kind === "expense").reduce((n, r) => n + Number(r.amount), 0);
              return (
                <section key={day}>
                  <h3 className="flex justify-between text-xs font-medium uppercase tracking-wide text-muted">
                    <span>{dayLabel(day, { weekday: "long", day: "numeric", month: "short" })}</span>
                    {spent > 0 && <span className="normal-case tracking-normal tabular-nums">{money(spent)} spent</span>}
                  </h3>
                  <ul className="divide-y divide-border">{rows.map((t) => <Row key={t.id} tx={t} today={today} />)}</ul>
                </section>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
