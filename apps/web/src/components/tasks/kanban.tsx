"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";
import { useState } from "react";
import { formatDue } from "@/lib/format";
import type { Project, Task, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTaskMutations } from "./hooks";

const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "todo", label: "To do" },
  { status: "in_progress", label: "In progress" },
  { status: "done", label: "Done" },
];

export function Kanban({ tasks, tz, projects }: { tasks: Task[]; tz: string; projects: Project[] }) {
  const { update, complete } = useTaskMutations();
  const [over, setOver] = useState<TaskStatus | null>(null);
  const move = (task: Task, status: TaskStatus) => {
    if (task.status === status) return;
    if (status === "done") complete.mutate(task.id);
    else update.mutate({ id: task.id, status });
  };
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {COLUMNS.map((col, ci) => {
        const items = tasks.filter((t) => t.status === col.status);
        return (
          <section
            key={col.status}
            aria-label={col.label}
            onDragOver={(e) => { e.preventDefault(); setOver(col.status); }}
            onDragLeave={() => setOver(null)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(null);
              const task = tasks.find((t) => t.id === e.dataTransfer.getData("text/task"));
              if (task) move(task, col.status);
            }}
            className={cn("min-h-40 rounded-xl border bg-surface/50 p-3", over === col.status ? "border-accent" : "border-border")}
          >
            <h2 className="mb-3 flex items-center justify-between text-sm font-medium">
              {col.label}<span className="text-xs text-muted">{items.length}</span>
            </h2>
            <ul className="space-y-2">
              {items.map((t) => {
                const due = formatDue(t, tz);
                const project = projects.find((p) => p.id === t.project_id);
                return (
                  <li key={t.id} draggable onDragStart={(e) => e.dataTransfer.setData("text/task", t.id)}
                    className="cursor-grab rounded-lg border border-border bg-surface p-3 text-sm active:cursor-grabbing">
                    <p className={cn(t.status === "done" && "text-muted line-through")}>{t.title}</p>
                    <p className="mt-1 flex flex-wrap gap-x-2 text-xs text-muted">
                      {due && <span className={cn(due.overdue && t.status !== "done" && "text-danger")}>{due.label}</span>}
                      {project && <span>{project.name}</span>}
                      {t.subtasks_total > 0 && <span>{t.subtasks_done}/{t.subtasks_total}</span>}
                    </p>
                    <div className="mt-2 flex justify-between">
                      <button disabled={ci === 0} onClick={() => move(t, COLUMNS[ci - 1].status)} className="rounded p-1 text-muted hover:bg-raised disabled:invisible" aria-label={`Move ${t.title} to ${COLUMNS[ci - 1]?.label}`}>
                        <ArrowLeft className="size-3.5" />
                      </button>
                      <button disabled={ci === COLUMNS.length - 1} onClick={() => move(t, COLUMNS[ci + 1].status)} className="rounded p-1 text-muted hover:bg-raised disabled:invisible" aria-label={`Move ${t.title} to ${COLUMNS[ci + 1]?.label}`}>
                        <ArrowRight className="size-3.5" />
                      </button>
                    </div>
                  </li>
                );
              })}
              {!items.length && <li className="py-6 text-center text-xs text-muted">Drop tasks here</li>}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
