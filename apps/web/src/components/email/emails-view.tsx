"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BellPlus, Inbox, Mail, RefreshCw, Reply, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { DraftEditor } from "@/components/email/draft-editor";
import { Button } from "@/components/ui/button";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EmailDetail, EmailDraft, EmailMessage, EmailSummary } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

type View = "needs_reply" | "important" | "inbox" | "sent" | "drafts";

const VIEWS: { id: View; label: string; count?: keyof EmailSummary }[] = [
  { id: "needs_reply", label: "Needs reply", count: "needs_reply" },
  { id: "important", label: "Important", count: "important" },
  { id: "inbox", label: "Inbox", count: "unread" },
  { id: "drafts", label: "Drafts", count: "drafts" },
  { id: "sent", label: "Sent" },
];

const CATEGORY_LABEL: Record<string, string> = {
  action: "Action",
  reply: "Reply",
  fyi: "FYI",
  newsletter: "Newsletter",
  promotion: "Promotion",
  other: "Other",
};

function message(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong. Try again.";
}

export function useEmailSummary() {
  return useQuery({ queryKey: ["email", "summary"], queryFn: () => api<EmailSummary>("/email/summary") });
}

function MessageRow({ m, active, onOpen, tz }: { m: EmailMessage; active: boolean; onOpen: () => void; tz: string }) {
  return (
    <li>
      <button
        onClick={onOpen}
        aria-current={active || undefined}
        className={cn("w-full rounded-lg px-3 py-2.5 text-left transition-colors", active ? "bg-accent/15" : "hover:bg-raised")}
      >
        <div className="flex items-baseline justify-between gap-2">
          <p className={cn("truncate text-sm", m.is_unread && "font-semibold")}>{m.from_name || m.from_addr}</p>
          <span className="shrink-0 text-[11px] text-muted">{formatDateTime(m.received_at, tz)}</span>
        </div>
        <p className="truncate text-sm">{m.subject || "(no subject)"}</p>
        <p className="mt-0.5 line-clamp-2 text-xs text-muted">{m.summary ?? m.snippet}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {m.priority === "high" && <span className="rounded bg-danger/15 px-1.5 text-[10px] font-medium text-danger">High</span>}
          {m.needs_reply && <span className="rounded bg-warn/15 px-1.5 text-[10px] font-medium text-warn">Needs reply</span>}
          {m.category && m.category !== "reply" && <span className="rounded bg-raised px-1.5 text-[10px] text-muted">{CATEGORY_LABEL[m.category]}</span>}
          {!m.triaged && <span className="rounded bg-raised px-1.5 text-[10px] text-muted">Not sorted yet</span>}
        </div>
      </button>
    </li>
  );
}

function MessageDetail({ id, onBack, tz }: { id: string; onBack: () => void; tz: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["email", "message", id], queryFn: () => api<EmailDetail>(`/email/messages/${id}`) });
  const [instructions, setInstructions] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["email"] });
  const aiDraft = useMutation({
    mutationFn: () => api<EmailDraft>(`/email/messages/${id}/draft`, { method: "POST", body: { instructions } }),
    onSuccess: () => {
      setInstructions("");
      setError(null);
      refresh();
    },
    onError: (e) => setError(message(e)),
  });
  const blank = useMutation({
    mutationFn: () => api<EmailDraft>("/email/drafts", { method: "POST", body: { reply_to_id: id, body: "" } }),
    onSuccess: refresh,
    onError: (e) => setError(message(e)),
  });
  const followUp = useMutation({
    mutationFn: (days: number) => api<{ title: string }>(`/email/messages/${id}/follow-up`, { method: "POST", body: { days } }),
    onSuccess: (r, days) => {
      setNotice(`Added “${r.title}” to your tasks, due in ${days} days.`);
      void qc.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (e) => setError(message(e)),
  });
  const correct = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/email/messages/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
  });

  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.isError || !q.data) return <Alert>Couldn&apos;t open this email.</Alert>;
  const m = q.data;
  const openDrafts = m.drafts.filter((d) => d.status !== "sent");
  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted hover:text-text lg:hidden">
        <ArrowLeft className="size-4" aria-hidden /> Back
      </button>
      <Card>
        <h2 className="text-lg font-semibold">{m.subject || "(no subject)"}</h2>
        <p className="mt-1 text-sm">
          {m.from_name} <span className="text-muted">&lt;{m.from_addr}&gt;</span>
        </p>
        <p className="text-xs text-muted">
          To {m.to.join(", ")}{m.cc?.length ? ` · Cc ${m.cc.join(", ")}` : ""} · {formatDateTime(m.received_at, tz)}
        </p>
        {m.summary && (
          <div className="mt-4 rounded-lg border border-accent/20 bg-accent/5 p-3 text-sm">
            <p className="flex items-center gap-1.5 text-xs font-medium text-accent"><Sparkles className="size-3.5" aria-hidden />Summary</p>
            <p className="mt-1">{m.summary}</p>
          </div>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={m.needs_reply} onChange={(e) => correct.mutate({ needs_reply: e.target.checked })} className="size-3.5 accent-accent" />
            Needs my reply
          </label>
          <label className="sr-only" htmlFor="prio">Priority</label>
          <select id="prio" value={m.priority} onChange={(e) => correct.mutate({ priority: e.target.value })} className="h-7 rounded border border-border bg-surface px-1">
            <option value="high">High priority</option>
            <option value="normal">Normal priority</option>
            <option value="low">Low priority</option>
          </select>
        </div>
        <pre className="mt-4 max-h-[50vh] overflow-y-auto whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">{m.body_text || m.snippet}</pre>
        {m.thread.length > 0 && <p className="mt-3 text-xs text-muted">{m.thread.length} other message(s) in this conversation.</p>}
      </Card>

      {notice && <Alert tone="good">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}

      {openDrafts.map((d) => <DraftEditor key={d.id} draft={d} />)}
      {m.drafts.filter((d) => d.status === "sent").map((d) => (
        <p key={d.id} className="text-sm text-good">You replied on {d.sent_at && formatDateTime(d.sent_at, tz)}.</p>
      ))}

      {!openDrafts.length && (
        <Card>
          <p className="text-sm font-medium">Reply</p>
          <label htmlFor="instr" className="sr-only">What should the reply say?</label>
          <textarea
            id="instr"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={2}
            placeholder="What should it say? For example: yes, Thursday works, ask for the agenda"
            className="mt-2 w-full resize-y rounded-lg border border-border bg-surface p-2 text-sm placeholder:text-muted/70 focus:border-accent"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={() => aiDraft.mutate()} loading={aiDraft.isPending}>
              <Sparkles className="size-4" aria-hidden /> Draft with AI
            </Button>
            <Button variant="secondary" onClick={() => blank.mutate()} loading={blank.isPending}>
              <Reply className="size-4" aria-hidden /> Write it myself
            </Button>
            <Button variant="ghost" onClick={() => followUp.mutate(3)} loading={followUp.isPending}>
              <BellPlus className="size-4" aria-hidden /> Remind me in 3 days
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted">Drafts are written on your PC. Nothing is sent until you approve it.</p>
        </Card>
      )}
    </div>
  );
}

function DraftsList({ tz }: { tz: string }) {
  const q = useQuery({ queryKey: ["email", "drafts"], queryFn: () => api<EmailDraft[]>("/email/drafts") });
  if (q.isLoading) return <Skeleton className="h-40" />;
  if (q.isError) return <Alert>Couldn&apos;t load drafts.</Alert>;
  if (!q.data?.length) return <p className="px-3 py-6 text-center text-sm text-muted">No drafts. Open an email and choose Draft with AI.</p>;
  return (
    <div className="space-y-3">
      {q.data.map((d) => (
        <div key={d.id}>
          <p className="mb-1 px-1 text-xs text-muted">Updated {formatDateTime(d.updated_at, tz)}</p>
          <DraftEditor draft={d} />
        </div>
      ))}
    </div>
  );
}

export function EmailsView() {
  const { user } = useAuth();
  const tz = user?.timezone ?? "UTC";
  const qc = useQueryClient();
  const [view, setView] = useState<View>("needs_reply");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const summary = useEmailSummary();
  const list = useQuery({
    queryKey: ["email", "list", view, search],
    queryFn: () => api<EmailMessage[]>(`/email/messages?view=${search ? "all" : view}${search ? `&q=${encodeURIComponent(search)}` : ""}`),
    enabled: view !== "drafts" && Boolean(summary.data?.connected),
  });
  const sync = useMutation({
    mutationFn: () => api<Record<string, unknown>>("/email/sync", { method: "POST" }),
    onSuccess: (r) => {
      const errs = ["gmail_error", "calendar_error", "triage_error"].map((k) => r[k]).filter(Boolean);
      setSyncError(errs.length ? errs.join(" ") : null);
      void qc.invalidateQueries({ queryKey: ["email"] });
      void qc.invalidateQueries({ queryKey: ["calendar"] });
    },
    onError: (e) => setSyncError(message(e)),
  });

  const sort = useMutation({
    mutationFn: () => api<{ triaged: number }>("/email/triage", { method: "POST" }),
    onSuccess: () => {
      setSyncError(null);
      void qc.invalidateQueries({ queryKey: ["email"] });
    },
    onError: (e) => setSyncError(message(e)),
  });

  if (summary.isLoading) return <Skeleton className="h-96" />;
  if (summary.isError || !summary.data) return <Alert>Couldn&apos;t load email.</Alert>;
  const s = summary.data;
  if (!s.connected) {
    return (
      <Card className="flex flex-col items-center gap-3 py-12 text-center">
        <Mail className="size-8 text-accent" aria-hidden />
        <p className="font-medium">{s.account_error ? "Google needs reconnecting" : "Connect Gmail to see your email here"}</p>
        <p className="max-w-md text-sm text-muted">
          {s.account_error ?? "NEXUS sorts your inbox on your PC, writes drafts, and sends only what you approve."}
        </p>
        <Link href="/settings/integrations" className="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-medium text-accent-fg hover:bg-accent/90">
          {s.account_error ? "Open integrations" : "Connect Google"}
        </Link>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Email views" className="flex flex-wrap gap-1">
          {VIEWS.map((v) => {
            const n = v.count ? s[v.count] : 0;
            return (
              <button
                key={v.id}
                role="tab"
                aria-selected={view === v.id && !search}
                onClick={() => {
                  setView(v.id);
                  setSearch("");
                  setQ("");
                  setOpen(null);
                }}
                className={cn("rounded-lg px-3 py-1.5 text-sm", view === v.id && !search ? "bg-accent/15 text-text" : "text-muted hover:bg-raised hover:text-text")}
              >
                {v.label}
                {typeof n === "number" && n > 0 && <span className="ml-1.5 text-xs text-muted">{n}</span>}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(q.trim());
              setOpen(null);
            }}
            className="relative"
          >
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted" aria-hidden />
            <label htmlFor="mail-q" className="sr-only">Search email</label>
            <input id="mail-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" className="h-9 w-44 rounded-lg border border-border bg-surface pl-8 pr-2 text-sm" />
          </form>
          <Button variant="secondary" className="h-9" onClick={() => sync.mutate()} loading={sync.isPending} aria-label="Sync now">
            <RefreshCw className="size-4" aria-hidden />
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted">
        {s.account_email} · {s.last_sync_at ? `synced ${formatDateTime(s.last_sync_at, tz)}` : "first sync running"}
        {s.untriaged > 0 && (
          <>
            {` · ${s.untriaged} waiting to be sorted `}
            <button onClick={() => sort.mutate()} disabled={sort.isPending} className="text-accent hover:underline disabled:opacity-60">
              {sort.isPending ? "Sorting…" : "Sort now"}
            </button>
          </>
        )}
      </p>
      {syncError && <Alert tone="warn">{syncError}</Alert>}

      {view === "drafts" && !search ? (
        <DraftsList tz={tz} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,380px)_1fr]">
          <Card className={cn("p-2", open && "hidden lg:block")}>
            {list.isLoading ? (
              <Skeleton className="h-64" />
            ) : list.isError ? (
              <Alert>Couldn&apos;t load messages.</Alert>
            ) : !list.data?.length ? (
              <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted">
                <Inbox className="size-6" aria-hidden />
                {search ? `Nothing matches “${search}”.` : view === "needs_reply" ? "No one is waiting on you." : "Nothing here."}
              </div>
            ) : (
              <ul className="max-h-[70vh] space-y-0.5 overflow-y-auto">
                {list.data.map((m) => <MessageRow key={m.id} m={m} active={open === m.id} onOpen={() => setOpen(m.id)} tz={tz} />)}
              </ul>
            )}
          </Card>
          <div className={cn(!open && "hidden lg:block")}>
            {open ? <MessageDetail id={open} onBack={() => setOpen(null)} tz={tz} /> : (
              <Card className="py-16 text-center text-sm text-muted">Pick an email to read it, see its summary and draft a reply.</Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
