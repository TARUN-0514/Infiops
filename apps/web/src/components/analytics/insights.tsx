"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarX2, Clock, Inbox, Repeat } from "lucide-react";
import Link from "next/link";
import { Empty } from "@/components/life/kit";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type Insight, type InsightKind, type InsightsResponse, severityTone } from "@/lib/analytics";
import { cn } from "@/lib/utils";

const ICONS: Record<InsightKind, typeof Clock> = {
  overdue: Clock,
  unanswered: Inbox,
  conflicts: CalendarX2,
  overloaded: AlertTriangle,
  postponed: Repeat,
};

export function useInsights() {
  return useQuery({ queryKey: ["insights"], queryFn: () => api<InsightsResponse>("/insights"), refetchInterval: 5 * 60_000 });
}

function InsightCard({ i, compact }: { i: Insight; compact?: boolean }) {
  const Icon = ICONS[i.kind];
  const tone = severityTone(i.severity);
  return (
    <li className="rounded-xl border border-border bg-surface/80 p-4">
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 rounded-lg p-1.5", tone === "danger" ? "bg-danger/15 text-danger" : tone === "warn" ? "bg-warn/15 text-warn" : "bg-raised text-muted")}>
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <p className="font-medium">{i.title}</p>
            <Link href={i.link} className="text-xs text-accent hover:underline">Open</Link>
          </div>
          {!compact && <p className="mt-0.5 text-xs text-muted">{i.detail}</p>}
          <ul className="mt-2 space-y-1">
            {i.items.slice(0, compact ? 3 : 8).map((x) => (
              <li key={x.id} className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
                <span className="min-w-0 truncate">{x.label}</span>
                <span className="shrink-0 text-xs text-muted">{x.sub}</span>
              </li>
            ))}
          </ul>
          {i.count > (compact ? 3 : 8) && <p className="mt-1 text-xs text-muted">and {i.count - (compact ? 3 : 8)} more</p>}
        </div>
      </div>
    </li>
  );
}

export function InsightsPanel() {
  const q = useInsights();
  return (
    <section aria-labelledby="insights-h">
      <h2 id="insights-h" className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Needs attention</h2>
      {q.isLoading ? <Skeleton className="h-28" /> : q.isError || !q.data ? (
        <Alert>Couldn&apos;t check for problems.</Alert>
      ) : !q.data.insights.length ? (
        <Empty>Nothing needs attention: no overdue tasks, email waiting over two days, conflicts, overloaded days or repeatedly postponed tasks.</Empty>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">{q.data.insights.map((i) => <InsightCard key={i.kind} i={i} />)}</ul>
      )}
    </section>
  );
}

export function InsightsHomeCard() {
  const q = useInsights();
  const list = q.data?.insights ?? [];
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Needs attention</CardTitle>
        <Link href="/analytics" className="text-xs text-accent hover:underline">Analytics</Link>
      </div>
      {q.isLoading ? <Skeleton className="mt-3 h-12" /> : q.isError ? (
        <div className="mt-3"><Alert>Couldn&apos;t check for problems.</Alert></div>
      ) : !list.length ? (
        <p className="mt-2 text-sm text-muted">All clear. Nothing overdue, waiting or clashing.</p>
      ) : (
        <ul className="mt-3 space-y-2">{list.slice(0, 2).map((i) => <InsightCard key={i.kind} i={i} compact />)}</ul>
      )}
    </Card>
  );
}
