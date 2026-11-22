"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Pencil, Play, Plus, Sparkles, Trash2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Bar, Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type Run, type Workflow, type WorkflowDraft, blankStep } from "@/lib/automation";
import { cn } from "@/lib/utils";
import { Builder } from "./builder";
import { useAutomationMeta, useRefreshAutomations } from "./hooks";
import { RunView, StatusPill } from "./run-view";

const BLANK: WorkflowDraft = { name: "", description: null, trigger: { type: "schedule", every: "day", at: "08:00", weekdays: [] }, steps: [blankStep("notify")], enabled: true };

function Describe({ onDraft }: { onDraft: (d: WorkflowDraft) => void }) {
  const [text, setText] = useState("");
  const draft = useMutation({ mutationFn: () => api<WorkflowDraft>("/automations/draft", { method: "POST", body: { prompt: text.trim() } }), onSuccess: onDraft });
  return (
    <Card>
      <CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-accent" aria-hidden />Describe an automation</CardTitle>
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 5) draft.mutate(); }} className="mt-3 space-y-2">
        <textarea aria-label="Describe what should happen" value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder="e.g. Every weekday at 8, list my tasks due today and send me a short summary" className={cn(inputCls, "h-auto w-full py-2")} />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" className="h-9" loading={draft.isPending} disabled={text.trim().length < 5}>Draft it</Button>
          <Button type="button" variant="ghost" className="h-9" onClick={() => onDraft(BLANK)}><Plus className="size-4" aria-hidden />Start from scratch</Button>
          <span className="text-xs text-muted">Your local model drafts it; you check and save it.</span>
        </div>
        {draft.isError && <Alert>{errorText(draft.error)}</Alert>}
      </form>
    </Card>
  );
}

function WorkflowCard({ w, onEdit, onRun }: { w: Workflow; onEdit: () => void; onRun: (r: Run) => void }) {
  const refresh = useRefreshAutomations();
  const toggle = useMutation({ mutationFn: () => api(`/automations/${w.id}`, { method: "PATCH", body: { enabled: !w.enabled } }), onSuccess: refresh });
  const run = useMutation({ mutationFn: () => api<Run>(`/automations/${w.id}/run`, { method: "POST" }), onSuccess: (r) => { refresh(); onRun(r); } });
  const [confirm, setConfirm] = useState(false);
  const remove = useMutation({ mutationFn: () => api(`/automations/${w.id}`, { method: "DELETE" }), onSuccess: refresh });
  const h = w.health;
  return (
    <li className={cn("rounded-xl border border-border bg-surface/80 p-4", !w.enabled && "opacity-70")}>
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{w.name}</p>
          <p className="text-xs text-muted">{w.trigger_label} · {w.step_count} step{w.step_count === 1 ? "" : "s"}{w.next_run_at && ` · next ${new Date(w.next_run_at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}`}</p>
        </div>
        <StatusPill s={w.last_status} />
        <label className="flex items-center gap-1.5 text-xs text-muted"><input type="checkbox" checked={toggle.isPending ? !w.enabled : w.enabled} disabled={toggle.isPending} onChange={() => toggle.mutate()} aria-label={`${w.name} turned on`} />On</label>
      </div>
      {w.description && <p className="mt-1 text-sm text-muted">{w.description}</p>}
      <div className="mt-3 flex items-center gap-2">
        <span className="w-28 shrink-0 text-xs text-muted">Last 14 days</span>
        {h.runs ? <><Bar pct={h.success_pct ?? 0} tone={h.failed ? "warn" : "good"} /><span className="w-28 shrink-0 text-right text-xs tabular-nums">{h.runs - h.failed}/{h.runs} without failing</span></> : <span className="text-xs text-muted">No runs yet</span>}
      </div>
      <div className="mt-3 flex flex-wrap gap-1">
        <Button variant="secondary" className="h-8 px-3" onClick={() => run.mutate()} loading={run.isPending}><Play className="size-3.5" aria-hidden />Run now</Button>
        <Button variant="ghost" className="h-8 px-3" onClick={onEdit}><Pencil className="size-3.5" aria-hidden />Edit</Button>
        {confirm ? (
          <>
            <Button variant="danger" className="h-8 px-3" onClick={() => remove.mutate()} loading={remove.isPending}>Delete {w.name}</Button>
            <Button variant="ghost" className="h-8 px-3" onClick={() => setConfirm(false)}>Keep</Button>
          </>
        ) : (
          <Button variant="ghost" className="h-8 px-3 hover:text-danger" onClick={() => setConfirm(true)}><Trash2 className="size-3.5" aria-hidden />Delete</Button>
        )}
      </div>
      {(run.isError || toggle.isError) && <div className="mt-2"><Alert>{errorText(run.error ?? toggle.error)}</Alert></div>}
    </li>
  );
}

function Runs({ selected, onOpen }: { selected: string | null; onOpen: (id: string) => void }) {
  const q = useQuery({ queryKey: ["automation-runs", "list"], queryFn: () => api<Run[]>("/automation-runs?limit=30") });
  if (q.isLoading) return <Skeleton className="h-32" />;
  if (q.isError) return <Alert>Couldn&apos;t load run history.</Alert>;
  if (!q.data?.length) return <Empty>No runs yet. Use Run now to try one.</Empty>;
  const waiting = q.data.filter((r) => r.status === "waiting_approval");
  const ordered = [...waiting, ...q.data.filter((r) => r.status !== "waiting_approval")];
  return (
    <ul className="divide-y divide-border">
      {ordered.map((r) => (
        <li key={r.id}>
          <button onClick={() => onOpen(r.id)} className={cn("flex w-full items-center gap-2 px-2 py-2 text-left hover:bg-raised/60", r.id === selected && "bg-accent/10")}>
            <span className="min-w-0 flex-1 truncate text-sm">{r.workflow}</span>
            <span className="text-xs text-muted">{new Date(r.started_at).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
            <StatusPill s={r.status} />
          </button>
        </li>
      ))}
    </ul>
  );
}

export function AutomationsView() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const meta = useAutomationMeta();
  const list = useQuery({ queryKey: ["automations", "list"], queryFn: () => api<Workflow[]>("/automations") });
  const [draft, setDraft] = useState<WorkflowDraft | null>(null);
  const editId = params.get("edit");
  const runId = params.get("run");
  const go = (p: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(p)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${path}${next.size ? `?${next}` : ""}`, { scroll: false });
  };
  const editing = useQuery({ queryKey: ["automations", "one", editId], queryFn: () => api<Workflow>(`/automations/${editId}`), enabled: Boolean(editId && editId !== "new") });

  if (meta.isLoading || list.isLoading) return <Skeleton className="h-64" />;
  if (meta.isError || !meta.data || list.isError) return <Alert>Couldn&apos;t load automations. Check that the API is running.</Alert>;

  if (editId === "new" && draft) {
    return <Builder key="new" start={draft} id={null} meta={meta.data} onDone={(w) => { setDraft(null); go({ edit: null, run: null }); void w; }} />;
  }
  if (editId && editId !== "new") {
    if (editing.isLoading) return <Skeleton className="h-64" />;
    if (editing.isError || !editing.data) return <Alert>That automation couldn&apos;t be loaded.</Alert>;
    return <Builder key={editId} start={editing.data} id={editId} meta={meta.data} onDone={() => go({ edit: null })} />;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_400px]">
      <div className="space-y-4">
        <Describe onDraft={(d) => { setDraft(d); go({ edit: "new" }); }} />
        {!list.data?.length ? (
          <Empty>No automations yet. Describe one above, or start from scratch.</Empty>
        ) : (
          <ul className="space-y-3">{list.data.map((w) => <WorkflowCard key={w.id} w={w} onEdit={() => go({ edit: w.id })} onRun={(r) => go({ run: r.id })} />)}</ul>
        )}
      </div>
      <div className="space-y-4">
        {runId && <RunView key={runId} id={runId} onClose={() => go({ run: null })} />}
        <Card>
          <CardTitle>Run history</CardTitle>
          <div className="mt-3"><Runs selected={runId} onOpen={(id) => go({ run: id })} /></div>
        </Card>
      </div>
    </div>
  );
}
