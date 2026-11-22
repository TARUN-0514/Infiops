"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs } from "@/components/life/kit";
import { Alert, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type Analytics, RANGES, parseRange } from "@/lib/analytics";
import { dayLabel } from "@/lib/calendar";
import { InsightsPanel } from "./insights";
import { HabitsGoalsSection, MoneyFitnessSection, TasksSection, TimeSection, WorkloadSection } from "./sections";

export function AnalyticsView() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const days = parseRange(params.get("days"));
  const q = useQuery({ queryKey: ["analytics", days], queryFn: () => api<Analytics>(`/analytics?days=${days}`) });
  return (
    <div className="space-y-6">
      <InsightsPanel />
      <div>
        <div className="flex flex-wrap items-center justify-between gap-x-4">
          <Tabs
            label="Period"
            tabs={RANGES.map((r) => ({ id: String(r.days), label: r.label }))}
            value={String(days)}
            onChange={(d) => router.replace(`${path}?days=${d}`, { scroll: false })}
          />
          {q.data && <p className="mb-6 text-sm text-muted">{dayLabel(q.data.range.from)} to {dayLabel(q.data.range.to)}</p>}
        </div>
        {q.isLoading ? (
          <div className="space-y-4"><Skeleton className="h-72" /><Skeleton className="h-48" /></div>
        ) : q.isError || !q.data ? (
          <Alert>Couldn&apos;t load analytics.</Alert>
        ) : (
          <div className="space-y-4">
            <TasksSection a={q.data} />
            <div className="grid gap-4 lg:grid-cols-2">
              <TimeSection a={q.data} />
              <WorkloadSection a={q.data} />
            </div>
            <HabitsGoalsSection a={q.data} />
            <MoneyFitnessSection a={q.data} />
            <p className="text-xs text-muted">Every number here comes from what you&apos;ve recorded in NEXUS. Money and health figures are worked out on your PC and are never sent to a cloud model.</p>
          </div>
        )}
      </div>
    </div>
  );
}
