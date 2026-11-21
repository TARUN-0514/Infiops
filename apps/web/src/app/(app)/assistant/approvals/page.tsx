"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApprovalCard } from "@/components/assistant/approval-card";
import { SectionTabs } from "@/components/assistant/section-tabs";
import { PageHeader } from "@/components/page-header";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { RISK_LABEL } from "@/lib/format";
import type { Approval } from "@/lib/types";
import { cn } from "@/lib/utils";

const FILTERS = ["pending", "approved", "rejected", "expired"] as const;

export default function ApprovalsPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("pending");
  const q = useQuery({ queryKey: ["approvals", filter], queryFn: () => api<Approval[]>(`/approvals?status=${filter}`) });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="AI Assistant" description="Actions that change or remove things wait here for your OK." />
      <SectionTabs />
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="flex gap-1" role="tablist" aria-label="Filter approvals">
          {FILTERS.map((f) => (
            <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
              className={cn("rounded-lg px-3 py-1.5 text-sm capitalize", filter === f ? "bg-raised text-text" : "text-muted hover:text-text")}>
              {f}
            </button>
          ))}
        </div>
        {q.isLoading ? <Skeleton className="h-24" /> : q.isError ? <Alert>Couldn&apos;t load approvals.</Alert> : !q.data?.length ? (
          <Card className="py-10 text-center text-sm text-muted">
            {filter === "pending" ? "Nothing is waiting for you." : `No ${filter} requests.`}
          </Card>
        ) : (
          <ul className="space-y-3">
            {q.data.map((a) => (
              <li key={a.id}>
                {a.status === "pending" ? <ApprovalCard approval={a} /> : (
                  <Card className="p-4">
                    <p className="text-sm font-medium">{a.summary}</p>
                    <p className="mt-0.5 text-xs text-muted">{RISK_LABEL[a.risk]} · {a.status} {a.decided_at ? `on ${new Date(a.decided_at).toLocaleString()}` : ""}</p>
                  </Card>
                )}
                {a.conversation_id && (
                  <Link href={`/assistant?c=${a.conversation_id}`} className="mt-1 inline-block text-xs text-accent hover:underline">Open the chat</Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
