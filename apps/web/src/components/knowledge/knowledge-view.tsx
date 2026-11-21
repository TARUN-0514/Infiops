"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Loader2, RotateCw, Search, Trash2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api, rawFetch } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { Citation, KbAnswer, KbDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.vtt,.srt,.json,.png,.jpg,.jpeg,.webp";

function message(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong. Try again.";
}

function UploadZone() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(0);
  const upload = async (files: FileList | File[]) => {
    setErrors([]);
    for (const file of Array.from(files)) {
      setBusy((n) => n + 1);
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await rawFetch("/knowledge/documents", { method: "POST", form });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          setErrors((e) => [...e, `${file.name}: ${body?.error?.message ?? "upload failed"}`]);
        }
      } catch {
        setErrors((e) => [...e, `${file.name}: upload failed`]);
      } finally {
        setBusy((n) => n - 1);
        void qc.invalidateQueries({ queryKey: ["kb"] });
      }
    }
  };
  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          void upload(e.dataTransfer.files);
        }}
        className={cn("flex flex-col items-center gap-2 rounded-xl border border-dashed p-6 text-center transition-colors", over ? "border-accent bg-accent/5" : "border-border")}
      >
        <Upload className="size-6 text-accent" aria-hidden />
        <p className="text-sm">Drop files here, or</p>
        <Button variant="secondary" onClick={() => input.current?.click()} loading={busy > 0}>
          Choose files
        </Button>
        <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => e.target.files && void upload(e.target.files)} />
        <p className="text-xs text-muted">PDF, Word, Excel, PowerPoint, text, Markdown, CSV, transcripts and images, up to 25 MB. Read on your PC.</p>
      </div>
      {errors.map((e) => <div key={e} className="mt-2"><Alert>{e}</Alert></div>)}
    </div>
  );
}

function Citations({ items }: { items: Citation[] }) {
  if (!items.length) return null;
  return (
    <ol className="mt-3 space-y-2 border-t border-border pt-3">
      {items.map((c) => (
        <li key={c.n} className="text-xs">
          <p className="font-medium">
            [{c.n}] {c.title}
            {c.where && <span className="font-normal text-muted"> · {c.where}</span>}
          </p>
          <p className="mt-0.5 line-clamp-3 text-muted">{c.excerpt}</p>
        </li>
      ))}
    </ol>
  );
}

function Ask() {
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ask = useMutation({
    mutationFn: (q: string) => api<KbAnswer>("/knowledge/ask", { method: "POST", body: { question: q } }),
    onSuccess: () => setError(null),
    onError: (e) => setError(message(e)),
  });
  return (
    <Card>
      <CardTitle>Ask your documents</CardTitle>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 3) ask.mutate(question.trim());
        }}
        className="mt-3 flex gap-2"
      >
        <label htmlFor="kb-q" className="sr-only">Question</label>
        <input id="kb-q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What does the runbook say about key rotation?" className="h-10 min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 text-sm" />
        <Button type="submit" loading={ask.isPending} disabled={question.trim().length < 3}>Ask</Button>
      </form>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      {ask.data && (
        <div className="mt-4 text-sm leading-relaxed">
          <Markdown text={ask.data.answer} />
          <Citations items={ask.data.citations} />
        </div>
      )}
    </Card>
  );
}

function DocDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["kb", "doc", id], queryFn: () => api<KbDocument>(`/knowledge/documents/${id}`) });
  const [confirm, setConfirm] = useState(false);
  const remove = useMutation({
    mutationFn: () => api(`/knowledge/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["kb"] });
      onClose();
    },
  });
  const reprocess = useMutation({
    mutationFn: () => api(`/knowledge/documents/${id}/reprocess`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["kb"] }),
  });
  const d = q.data;
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <CardTitle className="min-w-0 break-words">{d?.title ?? "Document"}</CardTitle>
        <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-raised" aria-label="Close"><X className="size-4" /></button>
      </div>
      {q.isLoading || !d ? <Skeleton className="mt-3 h-32" /> : (
        <div className="mt-2 space-y-3 text-sm">
          <p className="text-xs text-muted">{d.filename} · {formatBytes(d.size)}{d.pages ? ` · ${d.pages} page${d.pages > 1 ? "s" : ""}` : ""} · {d.chunks} passages</p>
          {d.error && <Alert>{d.error}</Alert>}
          {d.summary && <p>{d.summary}</p>}
          {!!d.preview?.length && (
            <details>
              <summary className="cursor-pointer text-xs text-muted">Extracted text</summary>
              <div className="mt-2 max-h-72 space-y-2 overflow-y-auto rounded-lg bg-bg p-2 text-xs">
                {d.preview.map((c) => (
                  <p key={c.ordinal} className="whitespace-pre-wrap">
                    {(c.label || c.page) && <span className="font-medium text-muted">{c.label ?? `Page ${c.page}`}: </span>}
                    {c.content}
                  </p>
                ))}
              </div>
            </details>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" className="h-8 px-3" onClick={() => reprocess.mutate()} loading={reprocess.isPending}><RotateCw className="size-3.5" aria-hidden />Read again</Button>
            {confirm ? (
              <Button variant="danger" className="h-8 px-3" onClick={() => remove.mutate()} loading={remove.isPending}>Delete permanently</Button>
            ) : (
              <Button variant="ghost" className="h-8 px-3" onClick={() => setConfirm(true)}><Trash2 className="size-3.5" aria-hidden />Delete…</Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export function KnowledgeView() {
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const docs = useQuery({
    queryKey: ["kb", "docs"],
    queryFn: () => api<KbDocument[]>("/knowledge/documents"),
    refetchInterval: (query) => (query.state.data?.some((d) => d.status === "processing") ? 2000 : false),
  });
  const hits = useQuery({
    queryKey: ["kb", "search", search],
    queryFn: () => api<Citation[]>(`/knowledge/search?q=${encodeURIComponent(search)}`),
    enabled: search.length >= 2,
  });
  const list = (docs.data ?? []).filter((d) => !filter || d.title.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <Ask />
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Documents</CardTitle>
            <form onSubmit={(e) => { e.preventDefault(); setSearch(filter.trim()); }} className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted" aria-hidden />
              <label htmlFor="kb-filter" className="sr-only">Search documents</label>
              <input id="kb-filter" value={filter} onChange={(e) => { setFilter(e.target.value); if (!e.target.value) setSearch(""); }} placeholder="Filter or search inside" className="h-9 w-56 rounded-lg border border-border bg-surface pl-8 pr-2 text-sm" />
            </form>
          </div>
          {search && (
            <div className="mt-3 rounded-lg border border-border p-3">
              <p className="text-xs text-muted">Passages matching “{search}”</p>
              {hits.isLoading ? <Skeleton className="mt-2 h-12" /> : !hits.data?.length ? <p className="mt-1 text-sm text-muted">No passages match.</p> : (
                <ul className="mt-2 space-y-2">
                  {hits.data.map((h) => (
                    <li key={`${h.document_id}-${h.n}`}>
                      <button onClick={() => setOpen(h.document_id)} className="text-left text-sm hover:text-accent">
                        <span className="font-medium">{h.title}</span>{h.where && <span className="text-muted"> · {h.where}</span>}
                        <span className="mt-0.5 block line-clamp-2 text-xs text-muted">{h.excerpt}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {docs.isLoading ? <Skeleton className="mt-3 h-32" /> : docs.isError ? <div className="mt-3"><Alert>Couldn&apos;t load documents.</Alert></div> : !list.length ? (
            <p className="mt-3 text-sm text-muted">{docs.data?.length ? "No titles match." : "No documents yet. Add your first file on the right."}</p>
          ) : (
            <ul className="mt-3 divide-y divide-border">
              {list.map((d) => (
                <li key={d.id}>
                  <button onClick={() => setOpen(d.id)} className={cn("flex w-full items-center gap-3 py-2.5 text-left", open === d.id && "text-accent")}>
                    <FileText className="size-4 shrink-0 text-muted" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">{d.title}</span>
                      <span className="block truncate text-xs text-muted">{d.summary ?? d.filename}</span>
                    </span>
                    {d.status === "processing" ? (
                      <span className="flex items-center gap-1 text-xs text-muted"><Loader2 className="size-3 animate-spin" aria-hidden />Reading</span>
                    ) : d.status === "failed" ? (
                      <span className="text-xs text-danger">Couldn&apos;t read</span>
                    ) : (
                      <span className="text-xs text-muted">{d.chunks} passages</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="space-y-4">
        <UploadZone />
        {open && <DocDetail id={open} onClose={() => setOpen(null)} />}
      </div>
    </div>
  );
}
