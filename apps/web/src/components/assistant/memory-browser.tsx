"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, History, Pencil, Plus, Trash2, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import type { MemoryCategory, MemoryConflict, MemoryItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORIES: MemoryCategory[] = ["profile", "preference", "work", "people", "health", "finance", "goal", "routine", "other"];

function useInvalidate() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["memory"] });
}

function AddMemory() {
  const invalidate = useInvalidate();
  const [content, setContent] = useState("");
  const [category, setCategory] = useState<MemoryCategory>("other");
  const add = useMutation({
    mutationFn: () => api<MemoryItem>("/memory", { method: "POST", body: { content, category } }),
    onSuccess: () => { setContent(""); invalidate(); },
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (content.trim().length >= 3) add.mutate(); }} className="flex flex-wrap gap-2">
      <label htmlFor="new-memory" className="sr-only">New memory</label>
      <input id="new-memory" value={content} onChange={(e) => setContent(e.target.value)} placeholder="Tell NEXUS something to remember, e.g. “I prefer meetings after 11am”"
        className="h-10 min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 text-sm" />
      <label htmlFor="new-memory-cat" className="sr-only">Category</label>
      <select id="new-memory-cat" value={category} onChange={(e) => setCategory(e.target.value as MemoryCategory)} className="h-10 rounded-lg border border-border bg-surface px-2 text-sm capitalize">
        {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <Button type="submit" loading={add.isPending} disabled={content.trim().length < 3}><Plus className="size-4" />Remember</Button>
      {add.isError && <p className="w-full text-sm text-danger" role="alert">{(add.error as ApiError).message}</p>}
    </form>
  );
}

function MemoryRow({ item, focused }: { item: MemoryItem; focused: boolean }) {
  const invalidate = useInvalidate();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.content);
  const [showHistory, setShowHistory] = useState(false);
  const [confirmForget, setConfirmForget] = useState(false);
  const history = useQuery({ queryKey: ["memory", "history", item.id], queryFn: () => api<MemoryItem[]>(`/memory/${item.id}/history`), enabled: showHistory });
  const edit = useMutation({ mutationFn: () => api(`/memory/${item.id}`, { method: "PATCH", body: { content: text } }), onSuccess: () => { setEditing(false); invalidate(); } });
  const confirm = useMutation({ mutationFn: () => api(`/memory/${item.id}/confirm`, { method: "POST" }), onSuccess: invalidate });
  const forget = useMutation({ mutationFn: () => api(`/memory/${item.id}`, { method: "DELETE" }), onSuccess: invalidate });
  const source = item.sources[0];
  return (
    <li id={`m-${item.id}`} className={cn("rounded-xl border bg-surface/80 p-4", focused ? "border-accent" : "border-border")}>
      {editing ? (
        <form onSubmit={(e) => { e.preventDefault(); edit.mutate(); }} className="flex gap-2">
          <label htmlFor={`edit-${item.id}`} className="sr-only">Edit memory</label>
          <input id={`edit-${item.id}`} value={text} onChange={(e) => setText(e.target.value)} className="h-9 flex-1 rounded-lg border border-border bg-bg px-2 text-sm" autoFocus />
          <Button type="submit" loading={edit.isPending} className="h-9">Save</Button>
          <Button type="button" variant="ghost" className="h-9" onClick={() => { setEditing(false); setText(item.content); }}>Cancel</Button>
        </form>
      ) : (
        <p className="text-sm">{item.content}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span className="rounded bg-raised px-1.5 py-0.5 capitalize">{item.category}</span>
        {item.status === "inferred" && <span className="rounded bg-warn/15 px-1.5 py-0.5 text-warn">Needs your confirmation</span>}
        {item.privacy !== "normal" && <span className="capitalize">{item.privacy}</span>}
        <span>Confidence {Math.round(item.confidence * 100)}%</span>
        <span>{source ? `From ${source.source_type === "chat" ? "a chat" : source.source_type}` : "No source"} · {new Date(item.created_at).toLocaleDateString()}</span>
        {item.version > 1 && <span>Version {item.version}</span>}
        {item.sources.length > 1 && <span>{item.sources.length} sources</span>}
      </div>
      {source?.excerpt && <p className="mt-1.5 border-l border-border pl-2 text-xs italic text-muted">“{source.excerpt}”</p>}
      <div className="mt-3 flex flex-wrap gap-1">
        {item.status === "inferred" && (
          <Button variant="secondary" className="h-8 px-3 text-xs" onClick={() => confirm.mutate()} loading={confirm.isPending}><Check className="size-3.5" />Confirm</Button>
        )}
        <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setEditing(true)}><Pencil className="size-3.5" />Edit</Button>
        {item.version > 1 && (
          <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setShowHistory((s) => !s)} aria-expanded={showHistory}><History className="size-3.5" />History</Button>
        )}
        {confirmForget ? (
          <span className="inline-flex items-center gap-1 text-xs">
            Forget this and its history?
            <Button variant="danger" className="h-8 px-2 text-xs" onClick={() => forget.mutate()} loading={forget.isPending}>Forget</Button>
            <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setConfirmForget(false)}><X className="size-3.5" /></Button>
          </span>
        ) : (
          <Button variant="ghost" className="h-8 px-2 text-xs hover:text-danger" onClick={() => setConfirmForget(true)}><Trash2 className="size-3.5" />Forget</Button>
        )}
      </div>
      {showHistory && (
        <ol className="mt-2 space-y-1 border-l border-border pl-3 text-xs text-muted">
          {history.isLoading ? <li>Loading…</li> : history.data?.map((v) => (
            <li key={v.id}>v{v.version}: {v.content} <span className="opacity-70">({new Date(v.created_at).toLocaleDateString()})</span></li>
          ))}
        </ol>
      )}
      {(edit.isError || confirm.isError || forget.isError) && <p className="mt-2 text-sm text-danger" role="alert">That didn&apos;t work. Try again.</p>}
    </li>
  );
}

function Conflicts() {
  const invalidate = useInvalidate();
  const q = useQuery({ queryKey: ["memory", "conflicts"], queryFn: () => api<MemoryConflict[]>("/memory/conflicts") });
  const resolve = useMutation({
    mutationFn: ({ id, keep }: { id: string; keep: "existing" | "candidate" }) => api(`/memory/conflicts/${id}/resolve`, { method: "POST", body: { keep } }),
    onSuccess: invalidate,
  });
  if (!q.data?.length) return null;
  return (
    <Card className="border-warn/30">
      <CardTitle>Which is right?</CardTitle>
      <p className="mt-1 text-sm text-muted">NEXUS heard something that may contradict what it remembers.</p>
      <ul className="mt-3 space-y-3">
        {q.data.map((c) => (
          <li key={c.id} className="grid gap-2 sm:grid-cols-2">
            <button onClick={() => resolve.mutate({ id: c.id, keep: "existing" })} className="rounded-lg border border-border p-3 text-left text-sm hover:border-accent">
              <span className="block text-xs text-muted">Keep what I know</span>{c.memory.content}
            </button>
            <button onClick={() => resolve.mutate({ id: c.id, keep: "candidate" })} className="rounded-lg border border-border p-3 text-left text-sm hover:border-accent">
              <span className="block text-xs text-muted">Use the new fact</span>{c.candidate.content}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MemoryBrowser() {
  const focus = useSearchParams().get("focus");
  const [category, setCategory] = useState<MemoryCategory | "all">("all");
  const [status, setStatus] = useState<"all" | "inferred">("all");
  const [q, setQ] = useState("");
  const params = new URLSearchParams();
  if (category !== "all") params.set("category", category);
  if (status === "inferred") params.set("status", "inferred");
  if (q.trim()) params.set("q", q.trim());
  const list = useQuery({ queryKey: ["memory", "list", params.toString()], queryFn: () => api<MemoryItem[]>(`/memory?${params}`) });
  const pendingCount = useQuery({ queryKey: ["memory", "list", "status=inferred"], queryFn: () => api<MemoryItem[]>("/memory?status=inferred") }).data?.length ?? 0;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <AddMemory />
      <Conflicts />
      <div className="flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search memory" aria-label="Search memory" className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 text-sm" />
        <label htmlFor="mem-cat" className="sr-only">Category</label>
        <select id="mem-cat" value={category} onChange={(e) => setCategory(e.target.value as MemoryCategory | "all")} className="h-9 rounded-lg border border-border bg-surface px-2 text-sm capitalize">
          <option value="all">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button onClick={() => setStatus((s) => (s === "all" ? "inferred" : "all"))} aria-pressed={status === "inferred"}
          className={cn("h-9 rounded-lg px-3 text-sm", status === "inferred" ? "bg-warn/15 text-warn" : "text-muted hover:bg-raised")}>
          To confirm{pendingCount ? ` (${pendingCount})` : ""}
        </button>
      </div>
      {list.isLoading ? (
        <div className="space-y-2"><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
      ) : list.isError ? (
        <Alert>Couldn&apos;t load memory.</Alert>
      ) : !list.data?.length ? (
        <Card className="py-10 text-center text-sm text-muted">
          {q || category !== "all" || status !== "all" ? "Nothing matches." : "NEXUS doesn't remember anything yet. Chat with it, or add a fact above."}
        </Card>
      ) : (
        <ul className="space-y-2">{list.data.map((m) => <MemoryRow key={m.id} item={m} focused={m.id === focus} />)}</ul>
      )}
    </div>
  );
}
