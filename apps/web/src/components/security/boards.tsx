"use client";

// AppSec, cloud and pentest boards, plus boards the owner makes: kanban by status.
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type FieldDef, type Item, type Workspace, byStatus, fieldKey, nextStatus, parseStatuses } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import { SeverityBadge, SlaBadge } from "./badges";
import { useRefreshWs } from "./hooks";
import { ItemPanel } from "./item-panel";

function NewBoard({ onDone }: { onDone: (id?: string) => void }) {
  const refresh = useRefreshWs();
  const [name, setName] = useState("");
  const [statuses, setStatuses] = useState("Backlog, Doing, Done");
  const [fields, setFields] = useState("");
  const [sla, setSla] = useState(false);
  const list = parseStatuses(statuses);
  const defs: FieldDef[] = parseStatuses(fields).map((label) => ({ key: fieldKey(label), label, type: "text" }));
  const make = useMutation({
    mutationFn: () => api<Workspace>("/workspaces", { method: "POST", body: { name: name.trim(), kind: "custom", statuses: list, closed: list.slice(-1), fields: defs, sla_days: sla ? { critical: 7, high: 30, medium: 90, low: 180 } : {} } }),
    onSuccess: (w) => { refresh(); onDone(w.id); },
  });
  return (
    <Card>
      <CardTitle>New board</CardTitle>
      <form onSubmit={(e) => { e.preventDefault(); make.mutate(); }} className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="text-xs text-muted">Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Red team" className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-xs text-muted">Statuses, in order; the last one means done<input value={statuses} onChange={(e) => setStatuses(e.target.value)} className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="text-xs text-muted">Extra fields, comma separated (optional)<input value={fields} onChange={(e) => setFields(e.target.value)} placeholder="Application, Environment" className={cn(inputCls, "mt-1 w-full")} /></label>
        <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" checked={sla} onChange={(e) => setSla(e.target.checked)} />Track SLA by severity (7, 30, 90, 180 days)</label>
        {make.isError && <div className="sm:col-span-2"><Alert>{errorText(make.error)}</Alert></div>}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" className="h-9" loading={make.isPending} disabled={!name.trim() || list.length < 2}>Create board</Button>
          <Button type="button" variant="ghost" className="h-9" onClick={() => onDone()}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

function AddCard({ ws, status }: { ws: Workspace; status: string }) {
  const refresh = useRefreshWs();
  const [title, setTitle] = useState("");
  const add = useMutation({ mutationFn: () => api(`/workspaces/${ws.id}/items`, { method: "POST", body: { title: title.trim(), status } }), onSuccess: () => { setTitle(""); refresh(); } });
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (title.trim()) add.mutate(); }} className="mt-2">
      <input aria-label={`Add a card to ${status}`} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="+ Add a card" className={cn(inputCls, "h-8 w-full bg-transparent")} />
      {add.isError && <p className="mt-1 text-xs text-danger">{errorText(add.error)}</p>}
    </form>
  );
}

function CardView({ ws, it, onOpen }: { ws: Workspace; it: Item; onOpen: () => void }) {
  const refresh = useRefreshWs();
  const next = nextStatus(ws, it.status);
  const move = useMutation({ mutationFn: () => api(`/workspace-items/${it.id}`, { method: "PATCH", body: { status: next } }), onSuccess: refresh });
  const extras = ws.fields.filter((f) => it.data[f.key] !== undefined).map((f) => `${f.label}: ${it.data[f.key]}`);
  return (
    <li className="rounded-lg border border-border bg-surface p-2.5">
      <button onClick={onOpen} className="w-full text-left">
        <p className="text-sm">{it.title}</p>
        {extras.length > 0 && <p className="mt-1 truncate text-xs text-muted">{extras.join(" · ")}</p>}
      </button>
      <div className="mt-2 flex items-center gap-2">
        {Object.keys(ws.sla_days).length > 0 && <SeverityBadge s={it.severity} />}
        <SlaBadge it={it} />
        {it.owner && <span className="truncate text-xs text-muted">{it.owner}</span>}
        {next && (
          <button onClick={() => move.mutate()} disabled={move.isPending} className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted hover:bg-raised hover:text-text" aria-label={`Move ${it.title} to ${next}`}>
            {next}<ArrowRight className="size-3" />
          </button>
        )}
      </div>
    </li>
  );
}

function Board({ ws, itemId, onOpen }: { ws: Workspace; itemId: string | null; onOpen: (id: string | null) => void }) {
  const refresh = useRefreshWs();
  const q = useQuery({ queryKey: ["ws", "items", ws.id, "board"], queryFn: () => api<Item[]>(`/workspaces/${ws.id}/items?state=all`) });
  const remove = useMutation({ mutationFn: () => api(`/workspaces/${ws.id}`, { method: "DELETE" }), onSuccess: refresh });
  const [confirm, setConfirm] = useState(false);
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError) return <Alert>Couldn&apos;t load this board.</Alert>;
  const groups = byStatus(ws, q.data ?? []);
  return (
    <div className="space-y-4">
      {itemId && <ItemPanel key={itemId} ws={ws} id={itemId} onClose={() => onOpen(null)} />}
      {!q.data?.length && <Empty>This board is empty. Add a card to any column.</Empty>}
      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
        {groups.map(([status, items]) => (
          <section key={status} className="w-64 shrink-0 rounded-xl border border-border bg-raised/40 p-2.5" aria-label={status}>
            <h3 className="flex items-center justify-between px-1 text-xs font-medium uppercase tracking-wide text-muted">{status}<span className="tabular-nums">{items.length}</span></h3>
            <ul className="mt-2 space-y-2">{items.map((it) => <CardView key={it.id} ws={ws} it={it} onOpen={() => onOpen(it.id)} />)}</ul>
            {!ws.closed.includes(status) && <AddCard ws={ws} status={status} />}
          </section>
        ))}
      </div>
      <div className="flex items-center gap-2">
        {confirm ? (
          <>
            <span className="text-xs text-muted">Delete {ws.name} and its {q.data?.length ?? 0} cards?</span>
            <Button variant="danger" className="h-7 px-2 text-xs" onClick={() => remove.mutate()} loading={remove.isPending}>Delete board</Button>
            <Button variant="ghost" className="h-7 px-2 text-xs" onClick={() => setConfirm(false)}>Keep it</Button>
          </>
        ) : (
          <Button variant="ghost" className="h-7 px-2 text-xs hover:text-danger" onClick={() => setConfirm(true)}><Trash2 className="size-3.5" aria-hidden />Delete board</Button>
        )}
      </div>
    </div>
  );
}

export function Boards({ boards, boardId, itemId, onPick, onOpen }: { boards: Workspace[]; boardId: string | null; itemId: string | null; onPick: (id: string) => void; onOpen: (id: string | null) => void }) {
  const [creating, setCreating] = useState(false);
  const current = boards.find((b) => b.id === boardId) ?? boards[0];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Boards">
        {boards.map((b) => (
          <button key={b.id} role="tab" aria-selected={b.id === current?.id} onClick={() => { setCreating(false); onPick(b.id); }} className={cn("rounded-lg px-3 py-1.5 text-sm", b.id === current?.id ? "bg-raised text-text" : "text-muted hover:bg-raised")}>
            {b.name}{b.open > 0 && <span className="ml-1.5 text-xs text-muted">{b.open}</span>}{b.breached > 0 && <span className="ml-1 text-xs text-danger">· {b.breached} late</span>}
          </button>
        ))}
        <Button variant="ghost" className="h-8 px-2" onClick={() => setCreating(true)}><Plus className="size-4" aria-hidden />New board</Button>
      </div>
      {creating ? <NewBoard onDone={(id) => { setCreating(false); if (id) onPick(id); }} /> : current ? <Board key={current.id} ws={current} itemId={itemId} onOpen={onOpen} /> : <Empty>No boards yet. Make one.</Empty>}
    </div>
  );
}
