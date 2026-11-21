"use client";

import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { describeRecurrence, formatDue, PRIORITY_LABEL } from "@/lib/format";
import type { ParsedTask } from "@/lib/types";
import { useTaskMutations } from "./hooks";

/** Type a sentence, see what NEXUS understood, then confirm. */
export function QuickAdd({ tz, projectId }: { tz: string; projectId?: string | null }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<ParsedTask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { create } = useTaskMutations();
  const parse = useMutation({
    mutationFn: (t: string) => api<ParsedTask>("/tasks/parse", { method: "POST", body: { text: t } }),
    onSuccess: (p) => { setPreview(p); setError(null); },
    onError: (e) => { setPreview(null); setError(e instanceof ApiError ? e.message : "Couldn't read that."); },
  });

  const save = async (p: ParsedTask | null) => {
    let project_id = projectId ?? p?.project_id ?? null;
    if (p?.project_name && !project_id) {
      const proj = await api<{ id: string }>("/projects", { method: "POST", body: { name: p.project_name } }).catch(() => null);
      project_id = proj?.id ?? null;
    }
    const body = p
      ? { title: p.title, notes: p.notes, due_at: p.due_at, all_day: p.all_day, priority: p.priority, recurrence: p.recurrence, subtasks: p.subtasks, project_id }
      : { title: text.trim(), project_id };
    await create.mutateAsync(body);
    setText("");
    setPreview(null);
    setError(null);
  };

  const due = preview ? formatDue(preview, tz) : null;
  return (
    <div className="space-y-2">
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 2) parse.mutate(text.trim()); }} className="flex gap-2">
        <label htmlFor="quick-add" className="sr-only">Add a task</label>
        <input id="quick-add" value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }} placeholder="Add a task in plain words: “pay rent on the 1st every month”"
          className="h-11 min-w-0 flex-1 rounded-xl border border-border bg-surface px-4 text-sm" />
        <Button type="submit" className="h-11" loading={parse.isPending} disabled={text.trim().length < 2}><Sparkles className="size-4" />Add</Button>
      </form>
      {preview && (
        <div className="rounded-xl border border-accent/30 bg-accent/5 p-3 text-sm" role="status">
          <p className="font-medium">{preview.title}</p>
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <span>{due ? due.label : "No date"}</span>
            {preview.recurrence && <span>{describeRecurrence(preview.recurrence)}</span>}
            {preview.priority !== "none" && <span>{PRIORITY_LABEL[preview.priority]}</span>}
            {preview.project_name && <span>Project: {preview.project_name}{preview.project_id ? "" : " (new)"}</span>}
            {preview.subtasks.length > 0 && <span>{preview.subtasks.length} subtasks</span>}
          </p>
          <div className="mt-2 flex gap-2">
            <Button className="h-8 px-3 text-xs" onClick={() => void save(preview)} loading={create.isPending}>Looks right, add it</Button>
            <Button variant="ghost" className="h-8 px-3 text-xs" onClick={() => setPreview(null)}>Cancel</Button>
          </div>
        </div>
      )}
      {error && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted" role="alert">
          <span className="text-danger">{error}</span>
          <Button variant="secondary" className="h-8 px-3 text-xs" onClick={() => void save(null)} loading={create.isPending}>Add “{text.trim().slice(0, 40)}” as is</Button>
        </div>
      )}
    </div>
  );
}
