import { describe, expect, it, vi } from "vitest";
import type { ChatEvent } from "@/lib/types";
import type { Mic, Player } from "./audio";
import { VoiceController, VoiceUnavailable, type VoiceDeps } from "./controller";

function tone(level: number, n = 1280) {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = level * Math.SQRT2 * Math.sin((2 * Math.PI * 440 * i) / 16000);
  return out;
}
const QUIET = tone(0.002);
const LOUD = tone(0.1);

class FakeMic implements Mic {
  rate = 16000;
  on: ((f: Float32Array) => void) | null = null;
  stopped = 0;
  async start(fn: (f: Float32Array) => void) {
    this.on = fn;
  }
  stop() {
    this.stopped++;
    this.on = null;
  }
}

class FakePlayer implements Player {
  played: ArrayBuffer[] = [];
  said: string[] = [];
  stops = 0;
  hold: Promise<void> | null = null;
  async play(wav: ArrayBuffer) {
    this.played.push(wav);
    if (this.hold) await this.hold;
  }
  async say(text: string) {
    this.said.push(text);
  }
  stop() {
    this.stops++;
  }
}

function setup(reply = "You have two meetings today. The first is at ten.", over: Partial<VoiceDeps> = {}) {
  const mic = new FakeMic();
  const player = new FakePlayer();
  const spoken: string[] = [];
  const asked: string[] = [];
  let t = 0;
  const deps: VoiceDeps = {
    mic,
    player,
    now: () => (t += 100),
    transcribe: vi.fn(async () => "What's on today?"),
    speak: async (s) => {
      spoken.push(s);
      return new ArrayBuffer(8);
    },
    newConversation: async () => "conv-1",
    ask: async (_cid: string, text: string, onEvent: (e: ChatEvent) => void) => {
      asked.push(text);
      for (const w of reply.split(" ")) onEvent({ type: "text.delta", text: w + " " });
    },
    ...over,
  };
  return { c: new VoiceController(deps), mic, player, spoken, asked, deps };
}

async function speakAndPause(mic: FakeMic) {
  for (let i = 0; i < 6; i++) mic.on?.(LOUD);
  for (let i = 0; i < 10; i++) mic.on?.(QUIET);
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("VoiceController", () => {
  it("runs a push-to-talk turn and speaks sentence by sentence", async () => {
    const { c, mic, player, spoken, asked } = setup();
    await c.press();
    expect(c.state.phase).toBe("listening");
    expect(c.state.micOn).toBe(true);
    await speakAndPause(mic);
    for (let i = 0; i < 10 && c.state.phase !== "idle"; i++) await flush();
    expect(asked).toEqual(["What's on today?"]);
    expect(spoken).toEqual(["You have two meetings today.", "The first is at ten."]);
    expect(player.played).toHaveLength(2);
    expect(c.state).toMatchObject({ phase: "idle", micOn: false, heard: "What's on today?", conversationId: "conv-1" });
    expect(c.state.latencyMs).toBeGreaterThan(0);
  });

  it("talking over the answer interrupts it and listens again", async () => {
    const { c, mic, player } = setup("A long answer that keeps going. And going on and on.");
    let release!: () => void;
    player.hold = new Promise((r) => (release = r));
    await c.press();
    await speakAndPause(mic);
    for (let i = 0; i < 10 && c.state.phase !== "speaking"; i++) await flush();
    expect(c.state.phase).toBe("speaking");
    for (let i = 0; i < 4; i++) mic.on?.(LOUD);
    await flush();
    expect(c.state.phase).toBe("listening");
    expect(player.stops).toBeGreaterThan(0);
    release();
  });

  it("falls back to the browser voice when the voice server is down", async () => {
    const { c, mic, player } = setup("Done. All set for tomorrow morning.", {
      speak: async () => {
        throw new VoiceUnavailable("down");
      },
    });
    await c.press();
    await speakAndPause(mic);
    for (let i = 0; i < 10 && c.state.phase !== "idle"; i++) await flush();
    expect(player.said).toEqual(["Done. All set for tomorrow morning."]);
    expect(c.state.fallbackVoice).toBe(true);
  });

  it("reports a blocked microphone and empty speech", async () => {
    const { c } = setup("", {
      mic: { rate: 16000, start: async () => { throw new DOMException("no", "NotAllowedError"); }, stop: () => {} },
    });
    await c.press();
    expect(c.state.phase).toBe("idle");
    expect(c.state.error).toMatch(/blocked/);

    const s2 = setup("", { transcribe: async () => "" });
    await s2.c.press();
    await speakAndPause(s2.mic);
    for (let i = 0; i < 10 && s2.c.state.phase !== "idle"; i++) await flush();
    expect(s2.c.state.error).toMatch(/didn't catch/);
  });

  it("pressing again while listening finishes or cancels", async () => {
    const { c, mic, asked } = setup();
    await c.press();
    await c.press(); // nothing said yet: cancel
    expect(c.state.phase).toBe("idle");
    expect(mic.stopped).toBe(1);
    await c.press();
    for (let i = 0; i < 4; i++) mic.on?.(LOUD);
    await c.press(); // finish now
    for (let i = 0; i < 10 && c.state.phase !== "idle"; i++) await flush();
    expect(asked).toHaveLength(1);
  });
});
