"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, Clock, Hand, Loader2, X, XCircle } from "lucide-react";
import { errorText } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { KIND_LABEL, type Run, type RunStep, STATUS_LABEL, statusTone, stepSummary } from "@/lib/automation";
import { cn } from "@/lib/utils";
import { useRefreshAutomations } from "./hooks";

export function StatusPill({ s }: { s: Run["status"] | null }) {
  if (!s) return <span className="text-xs text-muted">Never run</span>;
  const tone = statusTone(s);
  return <span className={cn("rounded-full px-2 py-0.5 text-xs", tone === "good" && "bg-good/15 text-good", tone === "danger" && "bg-danger/15 text-danger", tone === "warn" && "bg-warn/15 text-warn", tone === "muted" && "bg-raised text-muted")}>{STATUS_LABEL[s]}</span>;
}

function StepIcon({ s }: { s: RunStep }) {
  if (s.status === "succeeded") return <CheckCircle2 className="size-4 text-good" aria-label="Done" />;
  if (s.status === "failed") return <XCircle className="size-4 text-danger" aria-label="Failed" />;
  if (s.status === "waiting") return <Hand className="size-4 text-warn" aria-label="Waiting for you" />;
  if (s.status === "retrying") return <Clock className="size-4 text-warn" aria-label="Retrying" />;
  if (s.status === "running") return <Loader2 className="size-4 animate-spin text-accent" aria-label="Running" />;
  if (s.status === "declined") return <XCircle className="size-4 text-muted" aria-label="Declined" />;
  return <Circle className="size-4 text-muted/50" aria-label="Not run" />;
}

function output(s: RunStep): string | null {
  if (!s.output) return null;
  if (typeof s.output.text === "string") return s.output.text;
  if (s.kind === "condition") return s.output.passed ? "Condition met" : "Condition not met";
  if (s.kind === "notify") return "Notification sent";
  if (s.kind === "approval") return "You said go ahead";
  return JSON.stringify(s.output, null, 2);
}

export function RunView({ id, onClose }: { id: string; onClose: () => void }) {
  const refresh = useRefreshAutomations();
  const q = useQuery({
    queryKey: ["automation-runs", "one", id],
    queryFn: () => api<Run>(`/automation-runs/${id}`),
    refetchInterval: (query) => (["running", "queued"].includes(query.state.data?.status ?? "") ? 2000 : false),
  });
  const checkpoint = useMutation({ mutationFn: (approve: boolean) => api(`/automation-runs/${id}/decide`, { method: "POST", body: { approve } }), onSuccess: refresh });
  const tool = useMutation({ mutationFn: (v: { approval: string; approve: boolean }) => api(`/approvals/${v.approval}/decide`, { method: "POST", body: { approve: v.approve } }), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: () => api(`/automation-runs/${id}/cancel`, { method: "POST" }), onSuccess: refresh });
  if (q.isLoading) return <Card><Skeleton className="h-40" /></Card>;
  if (q.isError || !q.data) return <Card><Alert>That run couldn&apos;t be loaded.</Alert><Button variant="ghost" className="mt-2 h-8" onClick={onClose}>Close</Button></Card>;
  const r = q.data;
  const busy = checkpoint.isPending || tool.isPending;
  return (
    <Card aria-label="Run details" className="space-y-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{r.workflow}</p>
          <p className="text-xs text-muted">{new Date(r.started_at).toLocaleString()} · {r.trigger.type === "event" ? `after ${r.trigger.event}` : r.trigger.type === "schedule" ? "on schedule" : "run by you"}</p>
        </div>
        <StatusPill s={r.status} />
        <button onClick={onClose} className="rounded p-1.5 text-muted hover:bg-raised" aria-label="Close run"><X className="size-4" /></button>
      </div>
      {r.error && <Alert tone={r.status === "failed" ? "danger" : "warn"}>{r.error}</Alert>}
      {r.status === "retrying" && r.resume_at && <Alert tone="warn">Trying again at {new Date(r.resume_at).toLocaleTimeString()}.</Alert>}
      <ol className="space-y-2">
        {r.steps.map((s, i) => {
          const out = output(s);
          return (
            <li key={i} className="flex gap-2">
              <span className="mt-0.5"><StepIcon s={s} /></span>
              <div className="min-w-0 flex-1">
                <p className="text-sm">{i + 1}. {stepSummary(s)} <span className="text-xs text-muted">· {KIND_LABEL[s.kind]}{s.attempts > 1 ? ` · ${s.attempts} tries` : ""}</span></p>
                {s.error && <p className="text-xs text-danger">{s.error}</p>}
                {out && <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-raised/50 p-2 text-xs text-muted">{out}</pre>}
                {s.status === "waiting" && r.status === "waiting_approval" && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-warn/30 bg-warn/5 p-2">
                    <span className="text-sm">{s.message ?? (s.kind === "approval" ? "Go ahead?" : `Run ${String(s.config.tool)}?`)}</span>
                    <Button className="h-8" loading={busy} onClick={() => (s.approval_id ? tool.mutate({ approval: s.approval_id, approve: true }) : checkpoint.mutate(true))}>Go ahead</Button>
                    <Button variant="secondary" className="h-8" disabled={busy} onClick={() => (s.approval_id ? tool.mutate({ approval: s.approval_id, approve: false }) : checkpoint.mutate(false))}>Stop</Button>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {(checkpoint.isError || tool.isError || cancel.isError) && <Alert>{errorText(checkpoint.error ?? tool.error ?? cancel.error)}</Alert>}
      {["queued", "waiting_approval", "retrying"].includes(r.status) && <Button variant="ghost" className="h-8 text-xs" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel this run</Button>}
    </Card>
  );
}
