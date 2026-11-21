"use client";

import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

/** The Ask NEXUS command bar: anything typed here starts a chat. */
export function AskBar() {
  const router = useRouter();
  const [text, setText] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const q = text.trim();
        if (q) router.push(`/assistant?q=${encodeURIComponent(q)}`);
      }}
      className="flex items-center gap-2 rounded-2xl border border-border bg-surface p-2 pl-4 shadow-sm focus-within:border-accent/60"
    >
      <Sparkles className="size-5 shrink-0 text-accent" aria-hidden />
      <label htmlFor="ask" className="sr-only">Ask NEXUS</label>
      <input id="ask" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask NEXUS, or tell it what to do"
        className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted/70" />
      <button type="submit" disabled={!text.trim()} className="h-10 rounded-xl bg-accent px-4 text-sm font-medium text-accent-fg disabled:opacity-40">Ask</button>
    </form>
  );
}
