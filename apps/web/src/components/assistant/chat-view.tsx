"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, MessageSquarePlus, Search, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/markdown";
import { Alert, Skeleton } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { streamChat } from "@/lib/stream";
import type { AiStatus, Approval, ChatEvent, ChatMessage, Conversation, MemorySourceRef } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ApprovalCard } from "./approval-card";
import { Composer, type Attachment } from "./composer";
import { MessageBubble, Sources, ToolChips, type LiveTool } from "./message";

type ConversationDetail = { conversation: Conversation; messages: ChatMessage[]; pending_approvals: Approval[] };
type Draft = { user: ChatMessage; text: string; tools: LiveTool[]; sources: MemorySourceRef[]; provider: string };

function optimisticUser(text: string, attachments: Attachment[]): ChatMessage {
  return {
    id: `local-${Date.now()}`, conversation_id: "", role: "user", text, tools: [], sources: [], model: null, created_at: null,
    attachments: attachments.map((a) => ({ id: a.id, filename: a.filename, content_type: "" })),
  };
}

function ConversationList({ activeId, onPick, onNew }: { activeId: string | null; onPick: (id: string) => void; onNew: () => void }) {
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["conversations"], queryFn: () => api<Conversation[]>("/chat/conversations") });
  const search = useQuery({
    queryKey: ["chat-search", q],
    queryFn: () => api<{ conversation_id: string; conversation_title: string; snippet: string; message_id: string }[]>(`/chat/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 2,
  });
  return (
    <div className="flex h-full flex-col gap-3">
      <button onClick={onNew} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-raised">
        <MessageSquarePlus className="size-4" aria-hidden /> New chat
      </button>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted" aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" aria-label="Search chats" className="h-9 w-full rounded-lg border border-border bg-surface pl-8 pr-2 text-sm" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {q.trim().length >= 2 ? (
          search.isLoading ? <Skeleton className="h-16" /> : search.data?.length ? (
            <ul className="space-y-1">
              {search.data.map((h) => (
                <li key={h.message_id}>
                  <button onClick={() => onPick(h.conversation_id)} className="w-full rounded-lg px-2 py-2 text-left hover:bg-raised">
                    <p className="truncate text-sm">{h.conversation_title}</p>
                    <p className="line-clamp-2 text-xs text-muted">{h.snippet.replace(/[«»]/g, "")}</p>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="px-2 text-sm text-muted">No matches.</p>
        ) : list.isLoading ? (
          <div className="space-y-2"><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
        ) : list.isError ? (
          <Alert>Couldn&apos;t load chats.</Alert>
        ) : list.data?.length ? (
          <ul className="space-y-0.5">
            {list.data.map((c) => (
              <li key={c.id}>
                <button onClick={() => onPick(c.id)} aria-current={c.id === activeId ? "true" : undefined}
                  className={cn("w-full truncate rounded-lg px-2 py-2 text-left text-sm", c.id === activeId ? "bg-accent/15" : "text-muted hover:bg-raised hover:text-text")}>
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="px-2 text-sm text-muted">No chats yet.</p>}
      </div>
    </div>
  );
}

function ModelNotice({ status }: { status: AiStatus | undefined }) {
  if (!status || status.local.reachable) return null;
  return (
    <Alert tone="warn">
      NEXUS can&apos;t reach your local model at {status.local.base_url}. Start Ollama or LM Studio and load <strong>{status.local.models.chat}</strong>.
      {status.cloud.ready ? " You can also use the cloud for a message." : ""}
    </Alert>
  );
}

export function ChatView() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const activeId = params.get("c");
  const initialPrompt = params.get("q");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [liveApprovals, setLiveApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sentInitial = useRef(false);

  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => api<AiStatus>("/ai/status"), staleTime: 30_000 });
  const detail = useQuery({
    queryKey: ["conversation", activeId],
    queryFn: () => api<ConversationDetail>(`/chat/conversations/${activeId}`),
    enabled: !!activeId,
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [detail.data, draft?.text, draft?.tools.length, liveApprovals.length]);

  const send = useCallback(async (text: string, attachments: Attachment[], cloud: boolean) => {
    setError(null);
    setBusy(true);
    setLiveApprovals([]);
    let cid = activeId;
    try {
      if (!cid) {
        const conv = await api<Conversation>("/chat/conversations", { method: "POST" });
        cid = conv.id;
        router.replace(`/assistant?c=${cid}`);
      }
      setDraft({ user: optimisticUser(text, attachments), text: "", tools: [], sources: [], provider: cloud ? "cloud" : "local" });
      const onEvent = (e: ChatEvent) => {
        switch (e.type) {
          case "run.started":
            setDraft((d) => d && { ...d, user: e.user_message, provider: e.provider });
            break;
          case "memory.used":
            setDraft((d) => d && { ...d, sources: e.sources });
            break;
          case "text.delta":
            setDraft((d) => d && { ...d, text: d.text + e.text });
            break;
          case "tool.started":
            setDraft((d) => d && { ...d, tools: [...d.tools, { id: e.id, name: e.name, summary: e.summary, status: e.decision === "ask" ? "pending" : "running" }] });
            break;
          case "tool.finished":
            setDraft((d) => d && { ...d, tools: d.tools.map((t) => (t.id === e.id ? { ...t, status: e.status } : t)) });
            if (e.status === "succeeded") void qc.invalidateQueries({ queryKey: ["tasks"] });
            break;
          case "approval.required":
            setLiveApprovals((a) => [...a, e.approval]);
            void qc.invalidateQueries({ queryKey: ["approvals"] });
            break;
          case "error":
            setError(e.message);
            break;
        }
      };
      await streamChat(cid, { text, upload_ids: attachments.map((a) => a.id), cloud }, onEvent);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The reply was interrupted. Your message was saved; try again.");
    } finally {
      await qc.invalidateQueries({ queryKey: ["conversation", cid] });
      void qc.invalidateQueries({ queryKey: ["conversations"] });
      void qc.invalidateQueries({ queryKey: ["projects"] });
      setDraft(null);
      setBusy(false);
    }
  }, [activeId, qc, router]);

  useEffect(() => {
    if (initialPrompt && !sentInitial.current && !activeId) {
      sentInitial.current = true;
      void send(initialPrompt, [], false);
    }
  }, [initialPrompt, activeId, send]);

  const remove = async () => {
    if (!activeId) return;
    await api(`/chat/conversations/${activeId}`, { method: "DELETE" });
    void qc.invalidateQueries({ queryKey: ["conversations"] });
    router.replace("/assistant");
  };

  const messages = detail.data?.messages ?? [];
  const pending = [...(detail.data?.pending_approvals ?? []), ...liveApprovals.filter((a) => !detail.data?.pending_approvals.some((p) => p.id === a.id))];
  const empty = !activeId && !draft;

  return (
    <div className="grid h-[calc(100dvh-13rem)] min-h-[28rem] gap-4 lg:grid-cols-[240px_1fr]">
      <aside className="hidden lg:block">
        <ConversationList activeId={activeId} onPick={(id) => router.push(`/assistant?c=${id}`)} onNew={() => router.push("/assistant")} />
      </aside>
      <section className="flex min-h-0 flex-col gap-3" aria-label="Conversation">
        <div className="flex items-center justify-between gap-2 lg:hidden">
          <button onClick={() => router.push("/assistant")} className="inline-flex items-center gap-2 text-sm text-muted"><MessageSquarePlus className="size-4" />New chat</button>
        </div>
        {activeId && detail.data && (
          <div className="flex items-center justify-between gap-2">
            <h2 className="truncate text-sm font-medium text-muted">{detail.data.conversation.title}</h2>
            <button onClick={() => void remove()} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label="Delete this chat" title="Delete this chat">
              <Trash2 className="size-4" />
            </button>
          </div>
        )}
        <ModelNotice status={status.data} />
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1" aria-live="polite">
          {empty && (
            <div className="grid h-full place-items-center text-center">
              <div>
                <div className="mx-auto grid size-12 place-items-center rounded-xl bg-accent/15 text-accent"><Bot className="size-6" aria-hidden /></div>
                <p className="mt-3 font-medium">What can I do for you?</p>
                <p className="mt-1 text-sm text-muted">I can manage your tasks and projects and remember what matters to you.</p>
              </div>
            </div>
          )}
          {activeId && detail.isLoading && <div className="space-y-3"><Skeleton className="h-10 w-1/2 justify-self-end" /><Skeleton className="h-20" /></div>}
          {detail.isError && <Alert>Couldn&apos;t load this chat.</Alert>}
          {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
          {draft && (
            <>
              {!messages.some((m) => m.id === draft.user.id) && <MessageBubble message={draft.user} />}
              <div className="max-w-[92%]">
                <ToolChips tools={draft.tools} />
                {draft.text ? <Markdown text={draft.text} /> : (
                  <p className="flex items-center gap-2 text-sm text-muted">
                    <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden />
                    {draft.provider === "cloud" ? "Thinking in the cloud…" : "Thinking on your PC…"}
                  </p>
                )}
                <Sources sources={draft.sources} />
              </div>
            </>
          )}
          {pending.filter((a) => a.status === "pending").map((a) => (
            <ApprovalCard key={a.id} approval={a} onDecided={() => setLiveApprovals((l) => l.filter((x) => x.id !== a.id))} />
          ))}
          {error && <Alert>{error}</Alert>}
          <div ref={bottomRef} />
        </div>
        <Composer disabled={busy} status={status.data} onSend={(t, a, c) => void send(t, a, c)} />
      </section>
    </div>
  );
}
