/** Microphone capture and audio playback in the browser. */

import { FRAME_MS, Framer } from "./core";

export interface Mic {
  readonly rate: number;
  start(onFrame: (frame: Float32Array) => void): Promise<void>;
  stop(): void;
}

export interface Player {
  /** Plays one WAV clip; resolves when it ends or is stopped. */
  play(wav: ArrayBuffer): Promise<void>;
  /** Speaks text with the browser's own voice (used only when the voice server is down). */
  say(text: string): Promise<void>;
  stop(): void;
}

const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("nexus-tap", Tap);
`;

export class BrowserMic implements Mic {
  rate = 48000;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;

  async start(onFrame: (frame: Float32Array) => void) {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error(window.isSecureContext ? "This browser can't use the microphone." : "The microphone needs https:// or localhost.");
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    const ctx = new AudioContext();
    this.ctx = ctx;
    this.rate = ctx.sampleRate;
    const framer = new Framer(Math.round((ctx.sampleRate * FRAME_MS) / 1000));
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const source = ctx.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(ctx, "nexus-tap");
    node.port.onmessage = (e: MessageEvent<Float32Array>) => framer.push(e.data).forEach(onFrame);
    source.connect(node);
  }

  stop() {
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.ctx = null;
    this.stream = null;
  }
}

export class BrowserPlayer implements Player {
  private ctx: AudioContext | null = null;
  private source: AudioBufferSourceNode | null = null;
  private finish: (() => void) | null = null;

  private context() {
    this.ctx ??= new AudioContext();
    return this.ctx;
  }

  async play(wav: ArrayBuffer) {
    const ctx = this.context();
    if (ctx.state === "suspended") await ctx.resume();
    const buffer = await ctx.decodeAudioData(wav.slice(0));
    await new Promise<void>((resolve) => {
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      this.source = src;
      this.finish = resolve;
      src.onended = () => resolve();
      src.start();
    });
    this.source = null;
    this.finish = null;
  }

  say(text: string) {
    return new Promise<void>((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      u.onend = () => resolve();
      u.onerror = () => resolve();
      this.finish = resolve;
      window.speechSynthesis.speak(u);
    });
  }

  stop() {
    try {
      this.source?.stop();
    } catch {
      // already stopped
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    this.finish?.();
    this.source = null;
    this.finish = null;
  }
}
