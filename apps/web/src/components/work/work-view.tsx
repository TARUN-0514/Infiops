"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, FileBarChart, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Markdown } from "@/components/markdown";
import { useProjects } from "@/components/tasks/hooks";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import type { Briefing, WorkLogEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

function message(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong. Try again.";
}

const SOURCE_LABEL: Record<WorkLogEntry["source"], string> = { manual: "", task: "From a completed task", chat: "From chat" };

function AddEntry() {
  const qc = useQueryClient();
  const projects = useProjects();
  const [content, setContent] = useState("");
  const [minutes, setMinutes] = useState("");
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () =>
      api("/worklog", {
        method: "POST",
        body: { content: content.trim(), minutes: minutes ? Number(minutes) : null, project_id: projectId || null },
      }),
    onSuccess: () => {
      setContent("");
      setMinutes("");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["worklog"] });
    },
    onError: (e) => setError(message(e)),
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (content.trim().length >= 2) add.mutate();
      }}
      className="space-y-2"
    >
      <label htmlFor="log-content" className="sr-only">What did you work on?</label>
      <textarea id="log-content" value={content} onChange={(e) => setContent(e.target.value)} rows={2} placeholder="What did you work on? e.g. Triaged 14 scanner findings, 3 escalated" className="w-full resize-y rounded-lg border border-border bg-surface p-2 text-sm placeholder:text-muted/70" />
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="log-min">Minutes</label>
        <input id="log-min" type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} placeholder="Minutes" className="h-9 w-24 rounded-lg border border-border bg-surface px-2 text-sm" />
        <label className="sr-only" htmlFor="log-project">Project</label>
        <select id="log-project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 rounded-lg border border-border bg-surface px-2 text-sm">
          <option value="">No project</option>
          {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <Button type="submit" className="h-9" loading={add.isPending} disabled={content.trim().length < 2}>Log it</Button>
      </div>
      {error && <Alert>{error}</Alert>}
    </form>
  );
}

function EntryRow({ e }: { e: WorkLogEntry }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(e.content);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["worklog"] });
  const save = useMutation({ mutationFn: () => api(`/worklog/${e.id}`, { method: "PATCH", body: { content: text } }), onSuccess: () => { setEditing(false); refresh(); } });
  const remove = useMutation({ mutationFn: () => api(`/worklog/${e.id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <li className="group flex items-start gap-2 py-2">
      <div className="min-w-0 flex-1">
        {editing ? (
          <form onSubmit={(ev) => { ev.preventDefault(); save.mutate(); }} className="flex gap-2">
            <label htmlFor={`edit-${e.id}`} className="sr-only">Entry</label>
            <input id={`edit-${e.id}`} autoFocus value={text} onChange={(ev) => setText(ev.target.value)} className="h-8 min-w-0 flex-1 rounded-lg border border-border bg-surface px-2 text-sm" />
            <Button type="submit" className="h-8 px-2" loading={save.isPending} aria-label="Save"><Check className="size-4" /></Button>
          </form>
        ) : (
          <p className="text-sm">{e.content}</p>
        )}
        <p className="text-xs text-muted">
          {[e.minutes ? `${e.minutes} min` : null, e.project, SOURCE_LABEL[e.source] || null].filter(Boolean).join(" · ")}
        </p>
      </div>
      {!editing && (
        <div className="flex opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
          <button onClick={() => setEditing(true)} className="rounded p-1.5 text-muted hover:bg-raised" aria-label="Edit entry"><Pencil className="size-3.5" /></button>
          <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label="Delete entry"><Trash2 className="size-3.5" /></button>
        </div>
      )}
    </li>
  );
}

function WorkLog() {
  const q = useQuery({ queryKey: ["worklog"], queryFn: () => api<WorkLogEntry[]>("/worklog") });
  const byDay = new Map<string, WorkLogEntry[]>();
  for (const e of q.data ?? []) byDay.set(e.day, [...(byDay.get(e.day) ?? []), e]);
  return (
    <Card>
      <CardTitle>Work log</CardTitle>
      <p className="mt-1 text-sm text-muted">Completed tasks are logged for you. Add anything else you did.</p>
      <div className="mt-4"><AddEntry /></div>
      {q.isLoading ? <Skeleton className="mt-4 h-32" /> : q.isError ? <div className="mt-4"><Alert>Couldn&apos;t load the work log.</Alert></div> : !byDay.size ? (
        <p className="mt-4 text-sm text-muted">Nothing logged in the last two weeks.</p>
      ) : (
        <div className="mt-4 space-y-4">
          {[...byDay.entries()].map(([day, entries]) => {
            const total = entries.reduce((n, e) => n + (e.minutes ?? 0), 0);
            return (
              <section key={day}>
                <h3 className="text-xs font-medium uppercase tracking-wide text-muted">
                  {dayLabel(day, { weekday: "long", day: "numeric", month: "short" })}
                  {total > 0 && <span className="ml-2 normal-case tracking-normal">· {Math.floor(total / 60)}h {total % 60}m</span>}
                </h3>
                <ul className="divide-y divide-border">{entries.map((e) => <EntryRow key={e.id} e={e} />)}</ul>
              </section>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function Reports() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["reports"], queryFn: () => api<Briefing[]>("/reports") });
  const [openId, setOpenId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const make = useMutation({
    mutationFn: () => api<Briefing>("/reports", { method: "POST", body: {} }),
    onSuccess: (r) => {
      setOpenId(r.id);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (e) => setError(message(e)),
  });
  const current = q.data?.find((r) => r.id === openId) ?? q.data?.[0];
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2"><FileBarChart className="size-4 text-accent" aria-hidden />Weekly status</CardTitle>
        <Button className="h-8 px-3" onClick={() => make.mutate()} loading={make.isPending}>This week</Button>
      </div>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      {q.isLoading ? <Skeleton className="mt-3 h-24" /> : !current ? (
        <p className="mt-3 text-sm text-muted">Write a status report from this week&apos;s work log, meetings and tasks.</p>
      ) : (
        <div className="mt-3">
          {q.data && q.data.length > 1 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {q.data.map((r) => (
                <button key={r.id} onClick={() => setOpenId(r.id)} className={cn("rounded px-2 py-0.5 text-xs", r.id === current.id ? "bg-accent/15 text-text" : "text-muted hover:bg-raised")}>
                  {dayLabel(r.for_date, { day: "numeric", month: "short" })}
                </button>
              ))}
            </div>
          )}
          <div className="text-sm leading-relaxed"><Markdown text={current.content} /></div>
          <div className="mt-3 flex items-center justify-between border-t border-border pt-2">
            <p className="text-xs text-muted">{current.written_by_model ? `Written by ${current.model}` : "Written from the log without a model"} · week of {dayLabel(current.for_date, { day: "numeric", month: "short" })}</p>
            <Button
              variant="ghost"
              className="h-7 px-2 text-xs"
              onClick={() => {
                void navigator.clipboard.writeText(current.content).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              <Copy className="size-3.5" aria-hidden />{copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

export function WorkLogView() {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_400px]">
      <WorkLog />
      <Reports />
    </div>
  );
}
