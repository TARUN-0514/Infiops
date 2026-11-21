"use client";

import { useQuery } from "@tanstack/react-query";
import { Columns3, List } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Task } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useProjects } from "./hooks";
import { Kanban } from "./kanban";
import { QuickAdd } from "./quick-add";
import { TaskRow } from "./task-row";

type View = "list" | "board";

export function TaskBoard({ projectId }: { projectId?: string }) {
  const { user } = useAuth();
  const tz = user?.timezone ?? "UTC";
  const [view, setView] = useState<View>("list");
  const [showDone, setShowDone] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("nexus-task-view");
      if (saved === "list" || saved === "board") setView(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);
  const pick = (v: View) => {
    setView(v);
    try { localStorage.setItem("nexus-task-view", v); } catch { /* ignore */ }
  };
  const params = new URLSearchParams();
  const statuses = view === "board" || showDone ? ["todo", "in_progress", "done"] : ["todo", "in_progress"];
  statuses.forEach((s) => params.append("status", s));
  if (projectId) params.set("project_id", projectId);
  if (q.trim()) params.set("q", q.trim());
  const tasks = useQuery({ queryKey: ["tasks", "list", params.toString()], queryFn: () => api<Task[]>(`/tasks?${params}`) });
  const projects = useProjects().data ?? [];

  return (
    <div className="space-y-4">
      <QuickAdd tz={tz} projectId={projectId} />
      <div className="flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter tasks" aria-label="Filter tasks" className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 text-sm" />
        {view === "list" && (
          <label className="flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} className="size-4 accent-accent" /> Show done
          </label>
        )}
        <div className="flex rounded-lg border border-border p-0.5" role="group" aria-label="View">
          {(["list", "board"] as View[]).map((v) => {
            const Icon = v === "list" ? List : Columns3;
            return (
              <button key={v} onClick={() => pick(v)} aria-pressed={view === v} className={cn("inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm capitalize", view === v ? "bg-raised text-text" : "text-muted")}>
                <Icon className="size-4" aria-hidden />{v}
              </button>
            );
          })}
        </div>
      </div>
      {tasks.isLoading ? (
        <div className="space-y-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
      ) : tasks.isError ? (
        <Alert>Couldn&apos;t load tasks. {(tasks.error as Error).message}</Alert>
      ) : !tasks.data?.length && view === "list" ? (
        <Card className="py-10 text-center text-sm text-muted">{q ? "No tasks match." : "Nothing to do. Add a task above, or ask NEXUS in chat."}</Card>
      ) : view === "board" ? (
        <Kanban tasks={tasks.data ?? []} tz={tz} projects={projects} />
      ) : (
        <ul className="space-y-2">{tasks.data!.map((t) => <TaskRow key={t.id} task={t} tz={tz} projects={projects} compact={!!projectId} />)}</ul>
      )}
    </div>
  );
}
