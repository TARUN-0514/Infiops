"use client";

// One finding or card: status, owner, notes, follow-up, escalation and history.
import { useMutation, useQuery } from "@tanstack/react-query";
import { Trash2, X } from "lucide-react";
import { useState } from "react";
import { errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { SOURCE_LABEL, type ItemDetail, type Workspace } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import { SeverityBadge, SlaBadge } from "./badges";
import { useRefreshWs } from "./hooks";

const EVENT_LABEL: Record<string, string> = { created: "Added", status: "Changed", comment: "Note", escalated: "Escalated", follow_up: "Follow-up", imported: "Imported", reopened: "Reopened" };

function Escalate({ it, onDone }: { it: ItemDetail; onDone: () => void }) {
  const [to, setTo] = useState(it.owner ?? "");
  const [note, setNote] = useState("");
  const [follow, setFollow] = useState("");
  const send = useMutation({
    mutationFn: () => api(`/workspace-items/${it.id}/escalate`, { method: "POST", body: { to: to.trim(), note: note.trim(), follow_up_on: follow || null } }),
    onSuccess: onDone,
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); send.mutate(); }} className="space-y-2 rounded-lg border border-warn/30 bg-warn/5 p-3">
      <p className="text-xs text-muted">This records the escalation here. It doesn&apos;t email anyone; draft that from Emails if you need to.</p>
      <div className="flex flex-wrap gap-2">
        <input aria-label="Escalate to" value={to} onChange={(e) => setTo(e.target.value)} placeholder="Escalate to (person or team)" className={cn(inputCls, "min-w-0 flex-1")} />
        <input aria-label="Follow up on" type="date" value={follow} onChange={(e) => setFollow(e.target.value)} className={inputCls} />
      </div>
      <textarea aria-label="Reason" value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Why it needs attention" className={cn(inputCls, "h-auto w-full py-1.5")} />
      {send.isError && <Alert>{errorText(send.error)}</Alert>}
      <Button type="submit" className="h-8" loading={send.isPending} disabled={!to.trim() || !note.trim()}>Record escalation</Button>
    </form>
  );
}

function Fields({ ws, it, onSaved }: { ws: Workspace; it: ItemDetail; onSaved: () => void }) {
  const [data, setData] = useState<Record<string, string>>(Object.fromEntries(ws.fields.map((f) => [f.key, String(it.data[f.key] ?? "")])));
  const save = useMutation({ mutationFn: () => api(`/workspace-items/${it.id}`, { method: "PATCH", body: { data } }), onSuccess: onSaved });
  if (!ws.fields.length) return null;
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="grid gap-2 sm:grid-cols-2">
      {ws.fields.map((f) => (
        <label key={f.key} className="text-xs text-muted">
          {f.label}
          {f.type === "select" ? (
            <select aria-label={f.label} value={data[f.key]} onChange={(e) => setData({ ...data, [f.key]: e.target.value })} className={cn(inputCls, "mt-1 w-full")}>
              <option value="">Not set</option>
              {f.options?.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : (
            <input aria-label={f.label} type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"} value={data[f.key]} onChange={(e) => setData({ ...data, [f.key]: e.target.value })} className={cn(inputCls, "mt-1 w-full")} />
          )}
        </label>
      ))}
      {save.isError && <div className="sm:col-span-2"><Alert>{errorText(save.error)}</Alert></div>}
      <div className="sm:col-span-2"><Button type="submit" variant="secondary" className="h-8" loading={save.isPending}>Save fields</Button></div>
    </form>
  );
}

export function ItemPanel({ ws, id, onClose }: { ws: Workspace; id: string; onClose: () => void }) {
  const refresh = useRefreshWs();
  const q = useQuery({ queryKey: ["ws", "item", id], queryFn: () => api<ItemDetail>(`/workspace-items/${id}`) });
  const [note, setNote] = useState("");
  const [escalating, setEscalating] = useState(false);
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/workspace-items/${id}`, { method: "PATCH", body }),
    onSuccess: () => { setNote(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: () => api(`/workspace-items/${id}`, { method: "DELETE" }), onSuccess: () => { refresh(); onClose(); } });
  if (q.isLoading) return <Card><Skeleton className="h-48" /></Card>;
  if (q.isError || !q.data) return <Card><Alert>That item couldn&apos;t be loaded. It may have been deleted.</Alert><Button variant="ghost" className="mt-2 h-8" onClick={onClose}>Close</Button></Card>;
  const it = q.data;
  return (
    <Card className="space-y-4" aria-label="Item details">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><SeverityBadge s={it.severity} /><SlaBadge it={it} />{it.escalated_to && <span className="text-xs text-warn">Escalated to {it.escalated_to}</span>}</div>
          <h3 className="mt-1 break-words font-semibold">{it.title}</h3>
          <p className="text-xs text-muted">{[SOURCE_LABEL[it.source] ?? it.source, it.asset, it.identifier, `found ${dayLabel(it.found_on, { day: "numeric", month: "short", year: "numeric" })}`, `${it.age_days} days old`].filter(Boolean).join(" · ")}</p>
        </div>
        <button onClick={onClose} className="rounded p-1.5 text-muted hover:bg-raised" aria-label="Close details"><X className="size-4" /></button>
      </div>
      {it.description && <p className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg bg-raised/50 p-2 text-xs text-muted">{it.description}</p>}
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-xs text-muted">Status
          <select aria-label="Status" value={it.status} onChange={(e) => patch.mutate({ status: e.target.value })} className={cn(inputCls, "mt-1 w-full")}>
            {ws.statuses.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted">Severity
          <select aria-label="Severity" value={it.severity} onChange={(e) => patch.mutate({ severity: e.target.value })} className={cn(inputCls, "mt-1 w-full capitalize")}>
            {["critical", "high", "medium", "low", "info"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted">Follow up on
          <input aria-label="Follow-up date" type="date" defaultValue={it.follow_up_on ?? ""} onBlur={(e) => e.target.value !== (it.follow_up_on ?? "") && patch.mutate({ follow_up_on: e.target.value || null })} className={cn(inputCls, "mt-1 w-full")} />
        </label>
        <label className="text-xs text-muted sm:col-span-3">Owner
          <input aria-label="Owner" defaultValue={it.owner ?? ""} onBlur={(e) => e.target.value !== (it.owner ?? "") && patch.mutate({ owner: e.target.value || null })} placeholder="Who is fixing it" className={cn(inputCls, "mt-1 w-full")} />
        </label>
      </div>
      <Fields key={it.id} ws={ws} it={it} onSaved={refresh} />
      {patch.isError && <Alert>{errorText(patch.error)}</Alert>}
      <form onSubmit={(e) => { e.preventDefault(); if (note.trim()) patch.mutate({ note: note.trim() }); }} className="flex gap-2">
        <input aria-label="Add a note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note" className={cn(inputCls, "min-w-0 flex-1")} />
        <Button type="submit" variant="secondary" className="h-9" disabled={!note.trim()} loading={patch.isPending}>Add</Button>
      </form>
      {!it.closed && (escalating ? <Escalate it={it} onDone={() => { setEscalating(false); refresh(); }} /> : <Button variant="secondary" className="h-8" onClick={() => setEscalating(true)}>Escalate</Button>)}
      <section>
        <h4 className="text-xs font-medium uppercase tracking-wide text-muted">History</h4>
        <ol className="mt-2 space-y-1.5">
          {it.events.map((e, i) => (
            <li key={i} className="text-xs"><span className="font-medium">{EVENT_LABEL[e.kind] ?? e.kind}</span>{e.text && <span className="text-muted"> · {e.text}</span>}<span className="block text-muted/80">{new Date(e.at).toLocaleString()}</span></li>
          ))}
        </ol>
      </section>
      <Button variant="ghost" className="h-8 text-xs hover:text-danger" onClick={() => remove.mutate()} loading={remove.isPending}><Trash2 className="size-3.5" aria-hidden />Delete</Button>
    </Card>
  );
}
