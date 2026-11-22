"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { jobName, jobsOf, overallLabel, sortChecks, stateLabel, type CheckState, type StatusCheck, type SystemStatus } from "@/lib/status";
import { cn, formatDateTime } from "@/lib/utils";

export function useSystemStatus(refetchInterval = 60_000) {
  return useQuery({ queryKey: ["system-status"], queryFn: () => api<SystemStatus>("/status"), refetchInterval, staleTime: 30_000 });
}

const ICON: Record<CheckState, typeof CheckCircle2> = { ok: CheckCircle2, warn: AlertTriangle, error: XCircle, off: CircleDashed };
const TONE: Record<CheckState, string> = { ok: "text-good", warn: "text-warn", error: "text-danger", off: "text-muted" };

function CheckRow({ check, tz }: { check: StatusCheck; tz: string }) {
  const Icon = ICON[check.state];
  const jobs = check.key === "jobs" ? jobsOf(check) : [];
  return (
    <li className="flex items-start gap-3 py-3" data-check={check.key}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", TONE[check.state])} aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="font-medium">{check.label}</span>
          <span className={cn("text-xs", TONE[check.state])}>{stateLabel(check.state)}</span>
        </p>
        <p className="mt-0.5 break-words text-muted">{check.detail}</p>
        {jobs.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs">
            {jobs.map(([key, job]) => (
              <li key={key} className="flex flex-wrap justify-between gap-x-3">
                <span className={job.error ? "text-danger" : undefined}>{jobName(key)}</span>
                <span className="text-muted">
                  {job.error ? `failed ${job.failures}× · last ok ${job.last_ok ? formatDateTime(job.last_ok, tz) : "never"}` : `ok · ${formatDateTime(job.last_run, tz)}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

export function SystemStatusView() {
  const tz = useAuth().user?.timezone ?? "UTC";
  const q = useSystemStatus(30_000);
  if (q.isLoading) return <Card><Skeleton className="h-64" /></Card>;
  if (q.isError) {
    return (
      <Alert>
        {q.error instanceof ApiError ? q.error.message : "Couldn't reach the NEXUS server. If it's running on your PC, check that Docker is started."}
      </Alert>
    );
  }
  const s = q.data;
  if (!s) return null;
  const tone = s.overall === "ok" ? "text-good" : s.overall === "warn" ? "text-warn" : "text-danger";
  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className={tone}>{overallLabel(s)}</CardTitle>
            <p className="mt-1 text-xs text-muted">Checked {formatDateTime(s.checked_at, tz)}. Refreshes every 30 seconds.</p>
          </div>
          <Button variant="secondary" className="h-8 px-3" onClick={() => void q.refetch()} loading={q.isFetching}>Check again</Button>
        </div>
        <ul className="mt-2 divide-y divide-border">
          {sortChecks(s.checks).map((c) => <CheckRow key={c.key} check={c} tz={tz} />)}
        </ul>
      </Card>
      <Card>
        <CardTitle>Alerts</CardTitle>
        <p className="mt-1 text-sm text-muted">
          When a check fails twice in a row (about ten minutes), NEXUS sends you a notification, and another when it&apos;s fixed. A short blip never alerts you.
        </p>
      </Card>
    </>
  );
}
