import { rawFetch } from "./api";
import type { ChatEvent } from "./types";

/** Split a growing NDJSON buffer into complete events and the unfinished remainder. */
export function parseNdjson(buffer: string): { events: ChatEvent[]; rest: string } {
  const lines = buffer.split("\n");
  const rest = lines.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      events.push(JSON.parse(trimmed) as ChatEvent);
    } catch {
      // ignore a malformed line rather than breaking the whole stream
    }
  }
  return { events, rest };
}

export type SendBody = { text: string; upload_ids?: string[]; cloud?: boolean; privacy?: "normal" | "sensitive" | "secret" };

export async function streamChat(conversationId: string, body: SendBody, onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await rawFetch(`/chat/conversations/${conversationId}/messages`, { method: "POST", body });
  if (!res.body) throw new Error("Streaming isn't supported in this browser.");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    if (signal?.aborted) {
      await reader.cancel();
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseNdjson(buffer);
    buffer = rest;
    events.forEach(onEvent);
  }
  const { events } = parseNdjson(buffer + "\n");
  events.forEach(onEvent);
}
