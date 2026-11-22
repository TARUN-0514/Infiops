"use client";

// Vulnerability management: dashboard, filtered list, item details, add and import.
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { Bar, Empty, Stat, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { SEVERITIES, SOURCES, SOURCE_LABEL, type Item, type Severity, type Summary, type Workspace, severityShare } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import { SeverityBadge, SlaBadge } from "./badges";
import { useRefreshWs } from "./hooks";
import { ImportFindings } from "./import";
import { ItemPanel } from "./item-panel";

const BAR_TONE: Record<Severity, string> = { critical: "bg-danger", high: "bg-warn", medium: "bg-accent", low: "bg-muted/60", info: "bg-muted/30" };

function Dashboard({ ws }: { ws: Workspace }) {
  const q = useQuery({ queryKey: ["ws", "summary", ws.id], queryFn: () => api<Summary>(`/workspaces/${ws.id}/summary`) });
  if (q.isLoading) return <Skeleton className="h-28" />;
  if (q.isError || !q.data) return <Alert>Couldn&apos;t load the summary.</Alert>;
  const s = q.data;
  const share = severityShare(s);
  const maxAge = Math.max(1, ...Object.values(s.aging));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Open" value={String(s.open)} hint={`${s.closed} closed`} />
        <Stat label="Past SLA" value={String(s.breached)} tone={s.breached ? "danger" : undefined} />
        <Stat label="Due in 7 days" value={String(s.due_soon)} tone={s.due_soon ? "warn" : undefined} />
        <Stat label="Escalated" value={String(s.escalated)} />
        <Stat label="Mean days to close" value={s.mean_days_to_close === null ? "–" : String(s.mean_days_to_close)} />
        <Stat label="Closed within SLA" value={s.closed_in_sla_pct === null ? "–" : `${s.closed_in_sla_pct}%`} tone={s.closed_in_sla_pct !== null && s.closed_in_sla_pct >= 90 ? "good" : undefined} />
      </div>
      {s.open > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          <Card className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Open by severity</p>
            <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-raised" role="img" aria-label={share.map((x) => `${x.n} ${x.severity}`).join(", ")}>
              {share.map((x) => <div key={x.severity} className={BAR_TONE[x.severity]} style={{ width: `${x.pct}%` }} />)}
            </div>
            <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
              {share.map((x) => <li key={x.severity} className="capitalize"><span className={cn("mr-1 inline-block size-2 rounded-full", BAR_TONE[x.severity])} />{x.severity} {x.n}</li>)}
            </ul>
            <p className="mt-3 text-xs text-muted">{Object.entries(s.by_source).map(([k, n]) => `${SOURCE_LABEL[k] ?? k} ${n}`).join(" · ")}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Age of open findings</p>
            <ul className="mt-3 space-y-2">
              {Object.entries(s.aging).map(([bucket, n]) => (
                <li key={bucket} className="grid grid-cols-[4rem_1fr_2rem] items-center gap-2 text-xs">
                  <span className="text-muted">{bucket} days</span><Bar pct={(100 * n) / maxAge} tone={bucket === "90+" && n ? "danger" : "accent"} /><span className="text-right tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}

function AddFinding({ ws, onDone }: { ws: Workspace; onDone: () => void }) {
  const refresh = useRefreshWs();
  const [f, setF] = useState({ title: "", severity: "high" as Severity, source: "manual", asset: "", identifier: "", owner: "", found_on: "" });
  const add = useMutation({
    mutationFn: () => api(`/workspaces/${ws.id}/items`, { method: "POST", body: { ...f, title: f.title.trim(), asset: f.asset || null, identifier: f.identifier || null, owner: f.owner || null, found_on: f.found_on || null } }),
    onSuccess: () => { refresh(); onDone(); },
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="grid gap-2 sm:grid-cols-6">
      <input aria-label="Finding title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Finding, e.g. Outdated OpenSSL on web-01" className={cn(inputCls, "sm:col-span-6")} autoFocus />
      <select aria-label="Severity" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value as Severity })} className={cn(inputCls, "capitalize")}>{SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
      <select aria-label="Source" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} className={inputCls}>{SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}</select>
      <input aria-label="Asset" value={f.asset} onChange={(e) => setF({ ...f, asset: e.target.value })} placeholder="Asset" className={inputCls} />
      <input aria-label="CVE or rule" value={f.identifier} onChange={(e) => setF({ ...f, identifier: e.target.value })} placeholder="CVE or rule" className={inputCls} />
      <input aria-label="Owner" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} placeholder="Owner" className={inputCls} />
      <input aria-label="Found on" type="date" value={f.found_on} onChange={(e) => setF({ ...f, found_on: e.target.value })} className={inputCls} />
      {add.isError && <div className="sm:col-span-6"><Alert>{errorText(add.error)}</Alert></div>}
      <div className="flex gap-2 sm:col-span-6">
        <Button type="submit" className="h-9" loading={add.isPending} disabled={!f.title.trim()}>Add finding</Button>
        <Button type="button" variant="ghost" className="h-9" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

type Filters = { state: "open" | "closed" | "all"; severity: string; source: string; sla: string; q: string };

function Row({ it, active, onOpen }: { it: Item; active: boolean; onOpen: () => void }) {
  return (
    <li>
      <button onClick={onOpen} className={cn("flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-2 py-2.5 text-left hover:bg-raised/60", active && "bg-accent/10")}>
        <SeverityBadge s={it.severity} />
        <span className="min-w-0 flex-1 basis-48 truncate text-sm">{it.title}</span>
        <span className="hidden max-w-48 truncate text-xs text-muted md:inline">{it.asset}</span>
        <span className="text-xs text-muted">{it.status}</span>
        <SlaBadge it={it} />
      </button>
    </li>
  );
}

export function Findings({ ws, itemId, onOpen }: { ws: Workspace; itemId: string | null; onOpen: (id: string | null) => void }) {
  const [filters, setFilters] = useState<Filters>({ state: "open", severity: "", source: "", sla: "", q: "" });
  const [adding, setAdding] = useState(false);
  const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v) as [string, string][]);
  const q = useQuery({ queryKey: ["ws", "items", ws.id, params.toString()], queryFn: () => api<Item[]>(`/workspaces/${ws.id}/items?${params}`) });
  const set = (k: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setFilters({ ...filters, [k]: e.target.value });
  const filtered = Boolean(filters.severity || filters.source || filters.sla || filters.q || filters.state !== "open");
  return (
    <div className="space-y-4">
      <Dashboard ws={ws} />
      <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
        <Card className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Findings</CardTitle>
            {!adding && <Button className="h-8 px-3" onClick={() => setAdding(true)}><Plus className="size-4" aria-hidden />Add</Button>}
          </div>
          {adding && <div className="mt-3"><AddFinding ws={ws} onDone={() => setAdding(false)} /></div>}
          <div className="mt-3 flex flex-wrap gap-2">
            <div className="relative min-w-0 flex-1 basis-40">
              <Search className="absolute left-2 top-2.5 size-4 text-muted" aria-hidden />
              <input aria-label="Search findings" value={filters.q} onChange={set("q")} placeholder="Title, asset, CVE, owner" className={cn(inputCls, "w-full pl-8")} />
            </div>
            <select aria-label="Show" value={filters.state} onChange={set("state")} className={inputCls}><option value="open">Open</option><option value="closed">Closed</option><option value="all">All</option></select>
            <select aria-label="Filter by severity" value={filters.severity} onChange={set("severity")} className={cn(inputCls, "capitalize")}><option value="">Any severity</option>{SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
            <select aria-label="Filter by source" value={filters.source} onChange={set("source")} className={inputCls}><option value="">Any source</option>{SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}</select>
            <select aria-label="Filter by SLA" value={filters.sla} onChange={set("sla")} className={inputCls}><option value="">Any SLA</option><option value="breached">Past SLA</option><option value="due_soon">Due in 7 days</option></select>
          </div>
          <div className="mt-3">
            {q.isLoading ? <Skeleton className="h-40" /> : q.isError ? <Alert>Couldn&apos;t load findings.</Alert> : !q.data?.length ? (
              <Empty>{filtered ? "Nothing matches these filters." : "No open findings. Add one, or import an export from Inspector, GHAS, a DAST scanner or Guardium."}</Empty>
            ) : (
              <>
                <ul className="-mx-2 divide-y divide-border">{q.data.map((it) => <Row key={it.id} it={it} active={it.id === itemId} onOpen={() => onOpen(it.id)} />)}</ul>
                <p className="mt-2 text-xs text-muted">{q.data.length} shown</p>
              </>
            )}
          </div>
        </Card>
        <div className="space-y-4">
          {itemId ? <ItemPanel key={itemId} ws={ws} id={itemId} onClose={() => onOpen(null)} /> : <ImportFindings ws={ws} />}
        </div>
      </div>
    </div>
  );
}
