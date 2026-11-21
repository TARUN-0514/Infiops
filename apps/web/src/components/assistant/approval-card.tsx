"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { RISK_LABEL } from "@/lib/format";
import type { Approval, ChatMessage } from "@/lib/types";

type DecideResult = { approval: Approval; message: ChatMessage | null };

export function ApprovalCard({ approval, onDecided }: { approval: Approval; onDecided?: (r: DecideResult) => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const decide = useMutation({
    mutationFn: (approve: boolean) => api<DecideResult>(`/approvals/${approval.id}/decide`, { method: "POST", body: { approve } }),
    onSuccess: (r) => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["conversation"] });
      void qc.invalidateQueries({ queryKey: ["tasks"] });
      void qc.invalidateQueries({ queryKey: ["memory"] });
      onDecided?.(r);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't record your decision."),
  });
  const done = approval.status !== "pending";
  return (
    <div className="rounded-xl border border-warn/30 bg-warn/5 p-4" role="group" aria-label="Approval needed">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 size-5 shrink-0 text-warn" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{approval.summary}</p>
          <p className="mt-0.5 text-xs text-muted">
            {RISK_LABEL[approval.risk]} · needs your OK · expires {new Date(approval.expires_at).toLocaleString()}
          </p>
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer select-none">Details</summary>
            <pre className="mt-1 overflow-x-auto rounded bg-bg p-2 font-mono">{JSON.stringify(approval.input, null, 2)}</pre>
          </details>
          {error && <p className="mt-2 text-sm text-danger" role="alert">{error}</p>}
          {done ? (
            <p className="mt-3 text-sm text-muted">{approval.status === "approved" ? "Approved" : approval.status === "rejected" ? "Declined" : "Expired"}</p>
          ) : (
            <div className="mt-3 flex gap-2">
              <Button onClick={() => decide.mutate(true)} loading={decide.isPending && decide.variables === true} disabled={decide.isPending}>
                Approve
              </Button>
              <Button variant="secondary" onClick={() => decide.mutate(false)} loading={decide.isPending && decide.variables === false} disabled={decide.isPending}>
                Decline
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
