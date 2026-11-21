import { Brain, Check, CircleSlash, Loader2, Paperclip, Wrench, X } from "lucide-react";
import { Markdown } from "@/components/markdown";
import { TOOL_LABEL } from "@/lib/format";
import type { ChatMessage, MemorySourceRef } from "@/lib/types";
import { cn } from "@/lib/utils";

export type LiveTool = { id: string; name: string; summary: string; status: string };

export function Sources({ sources }: { sources: MemorySourceRef[] }) {
  if (!sources.length) return null;
  return (
    <details className="mt-2 text-xs text-muted">
      <summary className="flex cursor-pointer select-none items-center gap-1.5">
        <Brain className="size-3.5" aria-hidden /> Used {sources.length} {sources.length === 1 ? "memory" : "memories"}
      </summary>
      <ul className="mt-1.5 space-y-1 border-l border-border pl-3">
        {sources.map((s) => (
          <li key={s.id}>
            <a href={`/assistant/memory?focus=${s.id}`} className="hover:text-text">{s.content}</a>
            <span className="ml-1 opacity-70">({s.category})</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function ToolChips({ tools }: { tools: LiveTool[] }) {
  if (!tools.length) return null;
  return (
    <ul className="mb-2 flex flex-wrap gap-1.5" aria-label="Actions">
      {tools.map((t) => {
        const Icon = t.status === "running" ? Loader2 : t.status === "succeeded" ? Check : t.status === "pending" ? Wrench : t.status === "denied" ? CircleSlash : X;
        return (
          <li
            key={t.id}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
              t.status === "succeeded" ? "border-good/30 text-good" : t.status === "running" || t.status === "pending" ? "border-border text-muted" : "border-danger/30 text-danger",
            )}
          >
            <Icon className={cn("size-3", t.status === "running" && "animate-spin")} aria-hidden />
            {t.summary || TOOL_LABEL[t.name] || t.name}
            {t.status === "pending" && " · waiting for you"}
            {t.status === "failed" && " · failed"}
            {t.status === "denied" && " · blocked"}
            {t.status === "rejected" && " · declined"}
          </li>
        );
      })}
    </ul>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent/15 px-4 py-2.5 text-sm">
          {message.attachments.length > 0 && (
            <ul className="mb-1.5 flex flex-wrap gap-1.5 text-xs text-muted">
              {message.attachments.map((a) => (
                <li key={a.id} className="inline-flex items-center gap-1"><Paperclip className="size-3" aria-hidden />{a.filename}</li>
              ))}
            </ul>
          )}
          <p className="whitespace-pre-wrap">{message.text}</p>
        </div>
      </div>
    );
  }
  const tools: LiveTool[] = message.tools.map((t) => ({
    id: t.id, name: t.name, summary: TOOL_LABEL[t.name] ?? t.name, status: t.status === "pending_approval" ? "pending" : t.status,
  }));
  if (!message.text && !tools.length) return null;
  return (
    <div className="max-w-[92%]">
      <ToolChips tools={tools} />
      {message.text && <Markdown text={message.text} />}
      <Sources sources={message.sources} />
    </div>
  );
}
