"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApprovalCard } from "@/components/assistant/approval-card";
import { Button } from "@/components/ui/button";
import { Alert, Card } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import type { Approval, EmailDraft } from "@/lib/types";

const splitAddrs = (v: string) => v.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean);

export function DraftEditor({ draft }: { draft: EmailDraft }) {
  const qc = useQueryClient();
  const [to, setTo] = useState(draft.to.join(", "));
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [error, setError] = useState<string | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    setTo(draft.to.join(", "));
    setSubject(draft.subject);
    setBody(draft.body);
  }, [draft.id, draft.to, draft.subject, draft.body]);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["email"] });
    void qc.invalidateQueries({ queryKey: ["approvals"] });
  };
  const onError = (e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong.");
  const dirty = to !== draft.to.join(", ") || subject !== draft.subject || body !== draft.body;
  const save = useMutation({
    mutationFn: () => api<EmailDraft>(`/email/drafts/${draft.id}`, { method: "PATCH", body: { to: splitAddrs(to), subject, body } }),
    onSuccess: () => {
      setError(null);
      setSaved(true);
      refresh();
    },
    onError,
  });
  const send = useMutation({
    mutationFn: async () => {
      if (dirty) await save.mutateAsync();
      return api<{ approval: Approval }>(`/email/drafts/${draft.id}/send`, { method: "POST" });
    },
    onSuccess: (r) => {
      setError(null);
      setApproval(r.approval);
      refresh();
    },
    onError,
  });
  const discard = useMutation({ mutationFn: () => api(`/email/drafts/${draft.id}`, { method: "DELETE" }), onSuccess: refresh, onError });

  const locked = draft.status === "pending_approval";
  // The real approval request, so the card shows its true expiry and status.
  const pending = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api<Approval[]>("/approvals?status=pending"),
    enabled: locked && !approval,
  });
  const pendingApproval: Approval | null = approval ?? pending.data?.find((a) => a.id === draft.approval_id) ?? null;

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{draft.source === "ai" ? "Draft written by NEXUS" : "Your draft"}</p>
        <span className="text-xs text-muted">{draft.status === "failed" ? "Not sent" : locked ? "Waiting for your approval" : "Draft"}</span>
      </div>
      {draft.status === "failed" && draft.error && <Alert>{draft.error}</Alert>}
      <div className="grid gap-2 text-sm">
        <label className="grid grid-cols-[56px_1fr] items-center gap-2">
          <span className="text-muted">To</span>
          <input value={to} disabled={locked} onChange={(e) => { setTo(e.target.value); setSaved(false); }} className="h-9 rounded-lg border border-border bg-surface px-2 disabled:opacity-60" />
        </label>
        <label className="grid grid-cols-[56px_1fr] items-center gap-2">
          <span className="text-muted">Subject</span>
          <input value={subject} disabled={locked} onChange={(e) => { setSubject(e.target.value); setSaved(false); }} className="h-9 rounded-lg border border-border bg-surface px-2 disabled:opacity-60" />
        </label>
        <label className="sr-only" htmlFor={`body-${draft.id}`}>Message</label>
        <textarea
          id={`body-${draft.id}`}
          value={body}
          disabled={locked}
          onChange={(e) => { setBody(e.target.value); setSaved(false); }}
          rows={8}
          className="w-full resize-y rounded-lg border border-border bg-surface p-2 leading-relaxed disabled:opacity-60"
        />
      </div>
      {error && <Alert>{error}</Alert>}
      {locked && !pendingApproval && !pending.isLoading && <Alert tone="warn">This draft is waiting for approval. Open Approvals in the assistant to decide.</Alert>}
      {pendingApproval ? (
        <ApprovalCard
          approval={pendingApproval}
          onDecided={() => {
            setApproval(null);
            refresh();
          }}
        />
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => send.mutate()} loading={send.isPending} disabled={!body.trim() || !splitAddrs(to).length}>
            <Send className="size-4" aria-hidden /> Send…
          </Button>
          <Button variant="secondary" onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}>
            Save draft
          </Button>
          <Button variant="ghost" onClick={() => discard.mutate()} loading={discard.isPending} aria-label="Discard draft">
            <Trash2 className="size-4" aria-hidden />
          </Button>
          {saved && !dirty && <span className="text-xs text-good">Saved</span>}
        </div>
      )}
      <p className="text-xs text-muted">Send asks for your approval first. Nothing leaves your account until you approve.</p>
    </Card>
  );
}
