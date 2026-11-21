"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTaskMutations } from "@/components/tasks/hooks";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatDue } from "@/lib/format";
import type { Task } from "@/lib/types";
import { cn } from "@/lib/utils";

export function TodayCard({ tz }: { tz: string }) {
  const q = useQuery({ queryKey: ["tasks", "today"], queryFn: () => api<{ overdue: Task[]; today: Task[] }>("/tasks/today") });
  const { complete } = useTaskMutations();
  const items = [...(q.data?.overdue ?? []), ...(q.data?.today ?? [])];
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Today</CardTitle>
        <Link href="/tasks" className="text-xs text-accent hover:underline">All tasks</Link>
      </div>
      {q.isLoading ? <Skeleton className="mt-3 h-20" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load today&apos;s tasks.</Alert></div> : !items.length ? (
        <p className="mt-2 text-sm text-muted">Nothing due today.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.slice(0, 8).map((t) => {
            const due = formatDue(t, tz);
            return (
              <li key={t.id} className="flex items-start gap-2.5 text-sm">
                <input type="checkbox" onChange={() => complete.mutate(t.id)} aria-label={`Mark ${t.title} done`} className="mt-0.5 size-4 accent-accent" />
                <span className="min-w-0 flex-1">{t.title}</span>
                {due && <span className={cn("shrink-0 text-xs", due.overdue ? "text-danger" : "text-muted")}>{due.label.replace("Today, ", "")}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
