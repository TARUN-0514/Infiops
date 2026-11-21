"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cloud, ExternalLink, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LABEL_TEXT, citationParts, labelCounts } from "@/lib/operator";
import type { AiStatus, ResearchFinding, ResearchReport, ResearchSource } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

const LABEL_TONE: Record<ResearchFinding["label"], string> = {
  verified: "border-good/40 bg-good/10 text-good",
  assumption: "border-warn/40 bg-warn/10 text-warn",
  opinion: "border-accent/40 bg-accent/10 text-accent",
};

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function Cited({ text, sources }: { text: string; sources: ResearchSource[] }) {
  return (
    <>
      {citationParts(text).map((p, i) => {
        if (typeof p === "string") return <span key={i}>{p}</span>;
        const s = sources.find((x) => x.n === p);
        return s ? (
          <a key={i} href={s.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline" title={s.title}>[{p}]</a>
        ) : <span key={i}>[{p}]</span>;
      })}
    </>
  );
}

function Report({ r, tz }: { r: ResearchReport; tz: string }) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api(`/research/${r.id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["research"] }),
  });
  const counts = labelCounts(r.findings);
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle className="break-words">{r.question}</CardTitle>
          <p className="mt-0.5 text-xs text-muted">
            {formatDateTime(r.created_at, tz)} · {r.cloud ? "Cloud model" : "Local model"}
            {r.status === "done" && ` · ${counts.verified} verified, ${plural(counts.assumption, "assumption")}, ${plural(counts.opinion, "opinion")}`}
          </p>
        </div>
        <Button variant="ghost" className="h-8 w-8 shrink-0 px-0" aria-label="Delete report" onClick={() => remove.mutate()} loading={remove.isPending}>
          <Trash2 className="size-4" aria-hidden />
        </Button>
      </div>
      {r.status === "running" && (
        <div className="mt-3 space-y-2" role="status">
          <p className="text-sm text-muted">Searching and reading pages…</p>
          <Skeleton className="h-16" />
        </div>
      )}
      {r.status === "failed" && <div className="mt-3"><Alert>{r.error ?? "Research failed."}</Alert></div>}
      {r.status === "done" && (
        <>
          {r.summary && <p className="mt-3 text-sm leading-relaxed"><Cited text={r.summary} sources={r.sources} /></p>}
          <ul className="mt-3 space-y-2">
            {r.findings.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className={cn("mt-0.5 shrink-0 rounded border px-1.5 text-[11px] font-medium", LABEL_TONE[f.label])}>{LABEL_TEXT[f.label]}</span>
                <span className="min-w-0">
                  {f.claim}{" "}
                  {f.sources.map((n) => <Cited key={n} text={`[${n}]`} sources={r.sources} />)}
                  {f.note && <span className="block text-xs text-muted">{f.note}</span>}
                </span>
              </li>
            ))}
          </ul>
          {r.sources.length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-muted">Sources ({r.sources.filter((s) => s.read).length} read)</summary>
              <ol className="mt-2 space-y-1">
                {r.sources.map((s) => (
                  <li key={s.n} className="flex items-start gap-2 text-xs">
                    <span className="w-6 shrink-0 text-muted">[{s.n}]</span>
                    <span className="min-w-0">
                      <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 break-all text-accent hover:underline">
                        {s.title || s.url} <ExternalLink className="size-3 shrink-0" aria-hidden />
                      </a>
                      {!s.read && <span className="block text-danger">Couldn&apos;t read: {s.error}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </>
      )}
    </Card>
  );
}

export function ResearchView() {
  const tz = useAuth().user?.timezone ?? "UTC";
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [cloud, setCloud] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => api<AiStatus>("/ai/status") });
  const cloudReady = status.data?.cloud.ready ?? false;
  const q = useQuery({
    queryKey: ["research"],
    queryFn: () => api<ResearchReport[]>("/research"),
    refetchInterval: (query) => (query.state.data?.some((r) => r.status === "running") ? 2000 : false),
  });
  const start = useMutation({
    mutationFn: () => api<ResearchReport>("/research", { method: "POST", body: { question: question.trim(), cloud: cloud && cloudReady } }),
    onSuccess: () => {
      setQuestion("");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["research"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't start. Try again."),
  });
  const tooShort = question.trim().length < 5;
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card>
        <form onSubmit={(e) => { e.preventDefault(); if (!tooShort) start.mutate(); }} className="space-y-3">
          <label htmlFor="research-q" className="block text-sm font-medium">What should NEXUS find out?</label>
          <textarea id="research-q" rows={2} maxLength={1000} value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder="Which Ryzen 7 9700X cooler is quietest under 4,000 rupees?"
            className="w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted/70 focus:border-accent" />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" loading={start.isPending} disabled={tooShort}><Search className="size-4" aria-hidden /> Research</Button>
            <button type="button" disabled={!cloudReady} aria-pressed={cloud} onClick={() => setCloud((v) => !v)}
              title={cloudReady ? "Use the cloud model for a harder question" : "Cloud is off. Turn it on in Settings › AI."}
              className={cn("inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50", cloud ? "bg-accent/20 text-accent" : "text-muted hover:bg-raised hover:text-text")}>
              <Cloud className="size-4" aria-hidden /> Use cloud
            </button>
            <p className="text-xs text-muted">Findings are labelled verified (a page NEXUS read says so), assumption or opinion.</p>
          </div>
          {error && <Alert>{error}</Alert>}
        </form>
      </Card>
      {q.isLoading ? <Skeleton className="h-32" /> : q.isError ? <Alert>Couldn&apos;t load research.</Alert> : !q.data?.length ? (
        <Card className="py-10 text-center text-sm text-muted">No research yet. Ask a question above, or ask in chat.</Card>
      ) : (
        <div className="space-y-4">{q.data.map((r) => <Report key={r.id} r={r} tz={tz} />)}</div>
      )}
    </div>
  );
}
