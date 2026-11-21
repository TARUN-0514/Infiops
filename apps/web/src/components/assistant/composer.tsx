"use client";

import { Cloud, Paperclip, Send, X } from "lucide-react";
import { useRef, useState } from "react";
import { rawFetch, ApiError } from "@/lib/api";
import type { AiStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export type Attachment = { id: string; filename: string };

export function Composer({
  disabled, status, onSend, initial = "",
}: {
  disabled: boolean;
  status: AiStatus | undefined;
  onSend: (text: string, attachments: Attachment[], cloud: boolean) => void;
  initial?: string;
}) {
  const [text, setText] = useState(initial);
  const [cloud, setCloud] = useState(false);
  const [files, setFiles] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const cloudReady = status?.cloud.ready ?? false;

  const submit = () => {
    const value = text.trim();
    if (!value || disabled || uploading) return;
    onSend(value, files, cloud && cloudReady);
    setText("");
    setFiles([]);
    setCloud(false);
  };

  const upload = async (list: FileList | null) => {
    if (!list?.length) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of Array.from(list).slice(0, 5 - files.length)) {
        const form = new FormData();
        form.append("file", file);
        const res = await rawFetch("/uploads", { method: "POST", form });
        const body = (await res.json()) as Attachment;
        setFiles((f) => [...f, { id: body.id, filename: body.filename }]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-surface p-2 focus-within:border-accent/60">
      {files.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 px-2 pt-1">
          {files.map((f) => (
            <li key={f.id} className="inline-flex items-center gap-1 rounded-full bg-raised px-2.5 py-1 text-xs">
              <Paperclip className="size-3" aria-hidden />{f.filename}
              <button onClick={() => setFiles((x) => x.filter((y) => y.id !== f.id))} aria-label={`Remove ${f.filename}`} className="text-muted hover:text-text">
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <label htmlFor="composer" className="sr-only">Message NEXUS</label>
      <textarea
        id="composer"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={2}
        placeholder="Ask anything, or say what to do: “add a task to renew my passport next month”"
        className="block w-full resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted/70"
      />
      {error && <p className="px-2 text-xs text-danger" role="alert">{error}</p>}
      <div className="flex items-center gap-1 px-1">
        <input ref={fileRef} type="file" className="hidden" multiple accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,text/plain,text/markdown,text/csv" onChange={(e) => void upload(e.target.files)} />
        <button
          type="button" onClick={() => fileRef.current?.click()} disabled={uploading || files.length >= 5}
          className="rounded-lg p-2 text-muted hover:bg-raised hover:text-text disabled:opacity-50" aria-label="Attach a file" title="Attach images, PDFs or text (10 MB max)"
        >
          {uploading ? <span className="block size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Paperclip className="size-4" />}
        </button>
        <button
          type="button"
          onClick={() => setCloud((c) => !c)}
          disabled={!cloudReady}
          aria-pressed={cloud}
          title={cloudReady ? "Send this one message to the cloud model, for hard tasks" : "Cloud is off. Turn it on in Settings › AI to use it for hard tasks."}
          className={cn("inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50", cloud ? "bg-accent/20 text-accent" : "text-muted hover:bg-raised hover:text-text")}
        >
          <Cloud className="size-4" aria-hidden /> Use cloud
        </button>
        <span className="ml-auto mr-2 hidden text-xs text-muted sm:inline">{cloud ? "Cloud model, counts toward today's cap" : "Runs on your PC"}</span>
        <button
          type="button" onClick={submit} disabled={disabled || uploading || !text.trim()}
          className="grid size-9 place-items-center rounded-xl bg-accent text-accent-fg disabled:opacity-40" aria-label="Send"
        >
          <Send className="size-4" />
        </button>
      </div>
    </div>
  );
}
