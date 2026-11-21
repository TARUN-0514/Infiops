"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { KillSwitch } from "@/components/operator/kill-switch";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { RISK_LABEL, TOOL_LABEL } from "@/lib/format";
import type { ActivityItem } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

const STATUS: Record<ActivityItem["status"], { text: string; tone: string }> = {
  pending_approval: { text: "Waiting for you", tone: "text-warn" },
  running: { text: "Running", tone: "text-accent" },
  succeeded: { text: "Done", tone: "text-good" },
  failed: { text: "Failed", tone: "text-danger" },
  rejected: { text: "You declined", tone: "text-muted" },
  denied: { text: "Blocked by policy", tone: "text-danger" },
};

function Row({ a, tz }: { a: ActivityItem; tz: string }) {
  const [open, setOpen] = useState(false);
  const s = STATUS[a.status];
  return (
    <li className="py-3">
      <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{a.summary || TOOL_LABEL[a.tool] || a.tool}</p>
          <p className="mt-0.5 text-xs text-muted">
            <span className={s.tone}>{s.text}</span> · {RISK_LABEL[a.risk]} · {formatDateTime(a.created_at, tz)}
          </p>
          {a.error && <p className="mt-1 text-xs text-danger">{a.error}</p>}
        </div>
        <ChevronDown className={cn("mt-1 size-4 shrink-0 text-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-xs">
          <div>
            <p className="text-muted">Asked for</p>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-raised p-2">{JSON.stringify(a.input, null, 2)}</pre>
          </div>
          {a.output && (
            <div>
              <p className="text-muted">Result (shortened)</p>
              <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-raised p-2">{JSON.stringify(a.output, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function ActivityView() {
  const tz = useAuth().user?.timezone ?? "UTC";
  const q = useQuery({ queryKey: ["operator", "activity"], queryFn: () => api<ActivityItem[]>("/operator/activity"), refetchInterval: 10_000 });
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <KillSwitch />
      <p className="text-sm text-muted">
        Every action on your PC, the web and GitHub, newest first. Rules live in <Link className="text-accent hover:underline" href="/settings/computer">Settings › Computer control</Link>.
      </p>
      {q.isLoading ? <Skeleton className="h-40" /> : q.isError ? <Alert>Couldn&apos;t load the activity log.</Alert> : !q.data?.length ? (
        <Card className="py-10 text-center text-sm text-muted">Nothing yet. When NEXUS uses your PC, the web or GitHub, each step shows up here.</Card>
      ) : (
        <Card className="py-1"><ul className="divide-y divide-border">{q.data.map((a) => <Row key={a.id} a={a} tz={tz} />)}</ul></Card>
      )}
    </div>
  );
}
