"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cloud, Cpu } from "lucide-react";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { RISK_LABEL } from "@/lib/format";
import type { AiStatus, AiUsage, MemoryCategory, ToolInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

function Dot({ ok }: { ok: boolean }) {
  return <span className={cn("inline-block size-2 rounded-full", ok ? "bg-good" : "bg-muted")} aria-hidden />;
}

export function AiStatusCard() {
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => api<AiStatus>("/ai/status") });
  const usage = useQuery({ queryKey: ["ai-usage"], queryFn: () => api<AiUsage>("/ai/usage") });
  const s = status.data;
  return (
    <Card id="ai">
      <CardTitle>AI models</CardTitle>
      {status.isLoading ? <Skeleton className="mt-4 h-24" /> : status.isError || !s ? <div className="mt-4"><Alert>Couldn&apos;t check the AI models.</Alert></div> : (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border p-3">
            <p className="flex items-center gap-2 text-sm font-medium"><Cpu className="size-4 text-accent" aria-hidden />On your PC (default)</p>
            <p className="mt-2 flex items-center gap-2 text-sm"><Dot ok={s.local.reachable} />{s.local.reachable ? "Connected" : s.local.enabled ? "Not reachable" : "Turned off"}</p>
            <p className="mt-1 text-xs text-muted">{s.local.base_url}</p>
            <p className="mt-1 text-xs text-muted">Chat model: {s.local.models.chat}</p>
            {!s.local.reachable && s.local.enabled && <p className="mt-2 text-xs text-warn">Start Ollama or LM Studio and load {s.local.models.chat}.</p>}
          </div>
          <div className="rounded-lg border border-border p-3">
            <p className="flex items-center gap-2 text-sm font-medium"><Cloud className="size-4 text-accent" aria-hidden />Cloud (optional)</p>
            <p className="mt-2 flex items-center gap-2 text-sm"><Dot ok={s.cloud.ready} />{s.cloud.ready ? "Available per message" : s.cloud.enabled ? "On, but no API key is set" : "Off"}</p>
            <p className="mt-1 text-xs text-muted">Chat {s.cloud.models.chat} · Hard tasks {s.cloud.models.plan}</p>
            {usage.data && (
              <p className="mt-1 text-xs text-muted">
                Today: {usage.data.cloud_tokens_today.toLocaleString()} of {usage.data.cloud_daily_token_budget.toLocaleString()} cloud tokens
              </p>
            )}
            {!s.cloud.ready && (
              <p className="mt-2 text-xs text-muted">To turn it on, set NEXUS_CLOUD_ENABLED=true and NEXUS_ANTHROPIC_API_KEY in your .env, then restart.</p>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export function ToolPermissions() {
  const qc = useQueryClient();
  const tools = useQuery({ queryKey: ["tools"], queryFn: () => api<ToolInfo[]>("/tools") });
  const set = useMutation({
    mutationFn: ({ name, decision }: { name: string; decision: string }) => api(`/tools/${name}/permission`, { method: "PUT", body: { decision } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["tools"] }),
  });
  return (
    <Card id="permissions">
      <CardTitle>What NEXUS may do on its own</CardTitle>
      <p className="mt-1 text-sm text-muted">Sensitive actions ask first by default. Actions that can&apos;t be undone always ask, and forbidden ones never run.</p>
      {tools.isLoading ? <Skeleton className="mt-4 h-40" /> : tools.isError ? <div className="mt-4"><Alert>Couldn&apos;t load tools.</Alert></div> : (
        <ul className="mt-4 divide-y divide-border">
          {tools.data?.map((t) => (
            <li key={t.name} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <p className="text-sm">{t.description} <span className="font-mono text-xs text-muted">{t.name}</span></p>
                <p className="text-xs text-muted">{RISK_LABEL[t.risk]}</p>
              </div>
              <label className="sr-only" htmlFor={`perm-${t.name}`}>Permission for {t.name}</label>
              <select
                id={`perm-${t.name}`}
                value={t.policy ?? "default"}
                disabled={set.isPending}
                onChange={(e) => set.mutate({ name: t.name, decision: e.target.value })}
                className="h-8 rounded-lg border border-border bg-surface px-2 text-sm"
              >
                <option value="default">Default ({t.default === "allow" ? "allow" : "ask first"})</option>
                {t.risk !== "irreversible" && <option value="allow">Allow</option>}
                <option value="ask">Ask first</option>
                <option value="deny">Never</option>
              </select>
            </li>
          ))}
        </ul>
      )}
      {set.isError && <p className="mt-2 text-sm text-danger" role="alert">{(set.error as Error).message}</p>}
    </Card>
  );
}

const CATEGORY_LABEL: Record<MemoryCategory, string> = {
  profile: "About you", preference: "Preferences", work: "Work", people: "People", health: "Health",
  finance: "Money", goal: "Goals", routine: "Routines", other: "Other",
};

export function MemoryConsent() {
  const qc = useQueryClient();
  const consent = useQuery({ queryKey: ["memory", "consent"], queryFn: () => api<Record<MemoryCategory, string>>("/memory/consent") });
  const set = useMutation({
    mutationFn: (body: Partial<Record<MemoryCategory, string>>) => api("/memory/consent", { method: "PUT", body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["memory", "consent"] }),
  });
  return (
    <Card id="memory">
      <CardTitle>What NEXUS remembers from chats</CardTitle>
      <p className="mt-1 text-sm text-muted">“Save” stores facts you state directly. “Ask me” holds them for your confirmation. Guesses always wait for you.</p>
      {consent.isLoading ? <Skeleton className="mt-4 h-32" /> : consent.isError ? <div className="mt-4"><Alert>Couldn&apos;t load memory settings.</Alert></div> : (
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {(Object.keys(CATEGORY_LABEL) as MemoryCategory[]).map((c) => (
            <li key={c} className="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
              <label htmlFor={`consent-${c}`} className="text-sm">{CATEGORY_LABEL[c]}</label>
              <select id={`consent-${c}`} value={consent.data?.[c] ?? "ask"} onChange={(e) => set.mutate({ [c]: e.target.value })} className="h-8 rounded-lg border border-border bg-surface px-2 text-sm">
                <option value="auto">Save</option>
                <option value="ask">Ask me</option>
                <option value="off">Don&apos;t remember</option>
              </select>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
