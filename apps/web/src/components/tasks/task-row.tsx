"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ChevronDown, Repeat, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { describeRecurrence, formatDue, fromLocalInput, PRIORITY_LABEL, toLocalInput } from "@/lib/format";
import type { Priority, Project, Task } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTaskMutations } from "./hooks";

const PRIORITY_TONE: Record<Priority, string> = { none: "", low: "text-muted", medium: "text-accent", high: "text-warn", urgent: "text-danger" };

function Subtasks({ task }: { task: Task }) {
  const { create, complete, update } = useTaskMutations();
  const [title, setTitle] = useState("");
  const q = useQuery({ queryKey: ["tasks", "detail", task.id], queryFn: () => api<{ subtasks: Task[] }>(`/tasks/${task.id}`) });
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted">Subtasks</p>
      <ul className="space-y-1">
        {q.data?.subtasks.map((s) => (
          <li key={s.id} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={s.status === "done"} aria-label={`Mark ${s.title} done`}
              onChange={() => (s.status === "done" ? update.mutate({ id: s.id, status: "todo" }) : complete.mutate(s.id))} className="size-4 accent-accent" />
            <span className={cn(s.status === "done" && "text-muted line-through")}>{s.title}</span>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => { e.preventDefault(); if (title.trim()) create.mutate({ title: title.trim(), parent_task_id: task.id, project_id: task.project_id }, { onSuccess: () => setTitle("") }); }}>
        <label htmlFor={`sub-${task.id}`} className="sr-only">Add subtask</label>
        <input id={`sub-${task.id}`} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a subtask" className="h-8 w-full rounded-lg border border-border bg-bg px-2 text-sm" />
      </form>
    </div>
  );
}

function Editor({ task, tz, projects, onClose }: { task: Task; tz: string; projects: Project[]; onClose: () => void }) {
  const { update } = useTaskMutations();
  const [form, setForm] = useState({
    title: task.title, notes: task.notes ?? "", due: toLocalInput(task.due_at, tz), priority: task.priority,
    project_id: task.project_id ?? "", recurrence: task.recurrence ?? "",
  });
  const save = () =>
    update.mutate(
      {
        id: task.id, title: form.title, notes: form.notes || null, due_at: fromLocalInput(form.due, tz), all_day: false,
        priority: form.priority, project_id: form.project_id || null, recurrence: form.recurrence || null,
      },
      { onSuccess: onClose },
    );
  const field = "h-9 w-full rounded-lg border border-border bg-bg px-2 text-sm";
  return (
    <form onSubmit={(e) => { e.preventDefault(); save(); }} className="grid gap-3 sm:grid-cols-2">
      <label className="space-y-1 text-xs text-muted sm:col-span-2">Title
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={field} required maxLength={300} />
      </label>
      <label className="space-y-1 text-xs text-muted">Due
        <input type="datetime-local" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} className={field} />
      </label>
      <label className="space-y-1 text-xs text-muted">Priority
        <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value as Priority })} className={field}>
          {(Object.keys(PRIORITY_LABEL) as Priority[]).map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </select>
      </label>
      <label className="space-y-1 text-xs text-muted">Project
        <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} className={field}>
          <option value="">No project</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label className="space-y-1 text-xs text-muted">Repeat (RRULE)
        <input value={form.recurrence} onChange={(e) => setForm({ ...form, recurrence: e.target.value })} placeholder="FREQ=WEEKLY;BYDAY=MO" className={field} />
      </label>
      <label className="space-y-1 text-xs text-muted sm:col-span-2">Notes
        <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={2} className="w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-sm" />
      </label>
      {update.isError && <p className="text-sm text-danger sm:col-span-2" role="alert">{(update.error as Error).message}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" className="h-9" loading={update.isPending}>Save</Button>
        <Button type="button" variant="ghost" className="h-9" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}

export function TaskRow({ task, tz, projects, compact = false }: { task: Task; tz: string; projects: Project[]; compact?: boolean }) {
  const { complete, update, postpone, remove } = useTaskMutations();
  const [open, setOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const due = formatDue(task, tz);
  const project = projects.find((p) => p.id === task.project_id);
  const isDone = task.status === "done";
  return (
    <li className="rounded-xl border border-border bg-surface/80">
      <div className="flex items-start gap-3 p-3">
        <input type="checkbox" checked={isDone} aria-label={isDone ? `Mark ${task.title} not done` : `Mark ${task.title} done`}
          onChange={() => (isDone ? update.mutate({ id: task.id, status: "todo" }) : complete.mutate(task.id))}
          className="mt-0.5 size-4 shrink-0 accent-accent" />
        <button onClick={() => setOpen((o) => !o)} className="min-w-0 flex-1 text-left" aria-expanded={open}>
          <p className={cn("text-sm", isDone && "text-muted line-through")}>{task.title}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted">
            {due && <span className={cn("inline-flex items-center gap-1", due.overdue && !isDone && "text-danger")}><CalendarClock className="size-3" aria-hidden />{due.label}</span>}
            {task.recurrence && <span className="inline-flex items-center gap-1"><Repeat className="size-3" aria-hidden />{describeRecurrence(task.recurrence)}</span>}
            {task.priority !== "none" && <span className={PRIORITY_TONE[task.priority]}>{PRIORITY_LABEL[task.priority]}</span>}
            {!compact && project && <span>{project.name}</span>}
            {task.subtasks_total > 0 && <span>{task.subtasks_done}/{task.subtasks_total} subtasks</span>}
            {task.postponed_count >= 3 && <span className="text-warn">Postponed {task.postponed_count}×</span>}
          </p>
        </button>
        <ChevronDown className={cn("mt-0.5 size-4 shrink-0 text-muted transition-transform", open && "rotate-180")} aria-hidden />
      </div>
      {open && (
        <div className="space-y-4 border-t border-border p-3">
          <Editor task={task} tz={tz} projects={projects} onClose={() => setOpen(false)} />
          {!task.parent_task_id && <Subtasks task={task} />}
          <div className="flex flex-wrap gap-2">
            {!isDone && <Button variant="secondary" className="h-8 px-3 text-xs" onClick={() => postpone.mutate(task.id)} loading={postpone.isPending}>Postpone a day</Button>}
            {confirmDelete ? (
              <>
                <Button variant="danger" className="h-8 px-3 text-xs" onClick={() => remove.mutate(task.id)} loading={remove.isPending}>Delete for good</Button>
                <Button variant="ghost" className="h-8 px-3 text-xs" onClick={() => setConfirmDelete(false)}>Keep</Button>
              </>
            ) : (
              <Button variant="ghost" className="h-8 px-3 text-xs hover:text-danger" onClick={() => setConfirmDelete(true)}><Trash2 className="size-3.5" />Delete</Button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
