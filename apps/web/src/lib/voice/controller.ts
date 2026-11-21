/** One spoken conversation in the browser: push to talk, NEXUS answers out loud, and talking
 * over the answer interrupts it. Uses the same assistant (and tools) as chat. */

import type { ChatEvent } from "@/lib/types";
import { downsample, encodeWav, Endpointer, rms, SentenceSplitter, FRAME_MS } from "./core";
import type { Mic, Player } from "./audio";

export type VoicePhase = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

export type VoiceState = {
  phase: VoicePhase;
  micOn: boolean;
  heard: string;
  reply: string;
  error: string | null;
  /** End of your speech to the first sound of the answer, for the last turn. */
  latencyMs: number | null;
  waitingApproval: boolean;
  conversationId: string | null;
  /** The voice server was down, so the browser's own voice was used. */
  fallbackVoice: boolean;
};

export type VoiceDeps = {
  mic: Mic;
  player: Player;
  transcribe: (wav: ArrayBuffer) => Promise<string>;
  speak: (text: string) => Promise<ArrayBuffer>;
  newConversation: () => Promise<string>;
  ask: (conversationId: string, text: string, onEvent: (e: ChatEvent) => void, signal: AbortSignal) => Promise<void>;
  now?: () => number;
};

export class VoiceUnavailable extends Error {}

const BARGE_IN_MS = 240;

export class VoiceController {
  state: VoiceState = {
    phase: "idle",
    micOn: false,
    heard: "",
    reply: "",
    error: null,
    latencyMs: null,
    waitingApproval: false,
    conversationId: null,
    fallbackVoice: false,
  };
  private listeners = new Set<() => void>();
  private endpoint = new Endpointer();
  private turn: AbortController | null = null;
  private loudMs = 0;
  private threshold = 0.015;

  constructor(private readonly deps: VoiceDeps) {}

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  getState = () => this.state;

  private set(patch: Partial<VoiceState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }

  private now() {
    return this.deps.now ? this.deps.now() : performance.now();
  }

  /** The push-to-talk button: start listening, finish early, or interrupt the answer. */
  async press() {
    const { phase } = this.state;
    if (phase === "listening" && this.endpoint.started) return this.submit();
    if (phase === "listening") return this.close();
    if (phase !== "idle") this.interrupt();
    await this.listen();
  }

  async listen() {
    this.endpoint = new Endpointer(this.threshold);
    this.set({ phase: "listening", heard: "", reply: "", error: null, waitingApproval: false });
    if (this.state.micOn) return;
    try {
      await this.deps.mic.start((f) => this.feed(f));
      this.set({ micOn: true });
    } catch (e) {
      this.set({ phase: "idle", micOn: false, error: micError(e) });
    }
  }

  feed(frame: Float32Array) {
    const ms = (frame.length / this.deps.mic.rate) * 1000 || FRAME_MS;
    const { phase } = this.state;
    if (phase === "listening") {
      const r = this.endpoint.feed(frame, ms);
      if (r === "done") void this.submit();
      else if (r === "timeout") this.close();
    } else if (phase === "speaking" || phase === "thinking") {
      this.loudMs = rms(frame) >= this.threshold * 2 ? this.loudMs + ms : 0;
      if (this.loudMs >= BARGE_IN_MS) {
        this.loudMs = 0;
        this.interrupt();
        void this.listen().then(() => this.endpoint.feed(frame, ms));
      }
    }
  }

  /** Stop everything and close the microphone. */
  close() {
    this.interrupt();
    this.deps.mic.stop();
    this.set({ phase: "idle", micOn: false });
  }

  private interrupt() {
    this.turn?.abort();
    this.turn = null;
    this.deps.player.stop();
  }

  async submit() {
    const pcm = this.endpoint.audio();
    if (!pcm.length) return this.close();
    const ended = this.now();
    const controller = new AbortController();
    this.turn = controller;
    this.set({ phase: "transcribing" });
    try {
      const wav = encodeWav(downsample(pcm, this.deps.mic.rate));
      const text = (await this.deps.transcribe(wav)).trim();
      if (controller.signal.aborted) return;
      if (!text) {
        this.set({ error: "I didn't catch that. Try again." });
        return this.close();
      }
      this.set({ heard: text, phase: "thinking" });
      await this.answer(text, ended, controller);
    } catch (e) {
      if (controller.signal.aborted) return;
      this.set({ error: e instanceof Error ? e.message : "Voice failed." });
      this.close();
      return;
    }
    if (controller.signal.aborted) return;
    this.turn = null;
    this.close();
  }

  private async answer(text: string, ended: number, controller: AbortController) {
    const cid = this.state.conversationId ?? (await this.deps.newConversation());
    this.set({ conversationId: cid });
    const splitter = new SentenceSplitter();
    const queue: Promise<ArrayBuffer | string>[] = [];
    let first = true;
    let playing: Promise<void> = Promise.resolve();

    const fetchAudio = (s: string): Promise<ArrayBuffer | string> =>
      this.deps.speak(s).catch((e: unknown) => {
        if (e instanceof VoiceUnavailable) {
          this.set({ fallbackVoice: true });
          return s; // speak it with the browser's voice instead
        }
        return "";
      });

    const drain = async () => {
      while (queue.length && !controller.signal.aborted) {
        const clip = await queue.shift()!;
        if (controller.signal.aborted || !clip) continue;
        if (first) {
          first = false;
          this.set({ latencyMs: Math.round(this.now() - ended) });
        }
        this.set({ phase: "speaking" });
        await (typeof clip === "string" ? this.deps.player.say(clip) : this.deps.player.play(clip));
      }
    };

    const enqueue = (sentences: string[]) => {
      if (!sentences.length) return;
      sentences.forEach((s) => queue.push(fetchAudio(s)));
      playing = playing.then(drain);
    };

    await this.deps.ask(
      cid,
      text,
      (e) => {
        if (controller.signal.aborted) return;
        if (e.type === "text.delta") {
          this.set({ reply: this.state.reply + e.text });
          enqueue(splitter.feed(e.text));
        } else if (e.type === "approval.required") {
          this.set({ waitingApproval: true });
        } else if (e.type === "error") {
          this.set({ reply: e.message });
          enqueue([e.message]);
        }
      },
      controller.signal,
    );
    enqueue(splitter.flush());
    await playing;
  }
}

function micError(e: unknown): string {
  if (e instanceof DOMException && (e.name === "NotAllowedError" || e.name === "SecurityError")) {
    return "Microphone access is blocked. Allow it in the browser's site settings.";
  }
  if (e instanceof DOMException && e.name === "NotFoundError") return "No microphone found.";
  return e instanceof Error ? e.message : "Couldn't open the microphone.";
}
