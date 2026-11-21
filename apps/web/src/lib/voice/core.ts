/** Voice logic that doesn't need a microphone: levels, end-of-speech detection, WAV encoding
 * and sentence splitting. The same rules as the Windows local agent. */

export const TARGET_RATE = 16000;
export const FRAME_MS = 80;

export function rms(frame: Float32Array): number {
  if (!frame.length) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.sqrt(sum / frame.length);
}

export type EndpointResult = "waiting" | "speaking" | "done" | "timeout";

export class Endpointer {
  started = false;
  private loudMs = 0;
  private quietMs = 0;
  private totalMs = 0;
  private noise: number;
  frames: Float32Array[] = [];

  constructor(
    private readonly base = 0.015,
    private readonly startMs = 160,
    private readonly endMs = 800,
    private readonly maxMs = 15000,
    private readonly noSpeechMs = 7000,
  ) {
    this.noise = base / 3;
  }

  get threshold() {
    return Math.max(this.base, this.noise * 3);
  }

  feed(frame: Float32Array, ms = FRAME_MS): EndpointResult {
    const level = rms(frame);
    this.totalMs += ms;
    const loud = level >= this.threshold;
    if (!this.started) {
      this.frames = [...this.frames.slice(-3), frame];
      if (loud) {
        this.loudMs += ms;
        if (this.loudMs >= this.startMs) this.started = true;
      } else {
        this.loudMs = 0;
        this.noise = 0.95 * this.noise + 0.05 * level;
      }
      if (!this.started && this.totalMs >= this.noSpeechMs) return "timeout";
      return this.started ? "speaking" : "waiting";
    }
    this.frames.push(frame);
    this.quietMs = loud ? 0 : this.quietMs + ms;
    if (this.quietMs >= this.endMs || this.totalMs >= this.maxMs) return "done";
    return "speaking";
  }

  audio(): Float32Array {
    const length = this.frames.reduce((n, f) => n + f.length, 0);
    const out = new Float32Array(length);
    let offset = 0;
    for (const f of this.frames) {
      out.set(f, offset);
      offset += f.length;
    }
    return out;
  }
}

/** Averages samples down to the target rate (enough for speech recognition). */
export function downsample(input: Float32Array, fromRate: number, toRate = TARGET_RATE): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

export function encodeWav(samples: Float32Array, rate = TARGET_RATE): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset: number, s: string) => [...s].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

const SENTENCE_END = /(?<=[.!?])\s+(?=[A-Z0-9"'(])|\n{2,}/g;

/** Hands back whole sentences from streamed text so speech can start early. */
export class SentenceSplitter {
  private buf = "";
  constructor(private readonly minChars = 12) {}

  feed(text: string): string[] {
    this.buf += text;
    const out: string[] = [];
    for (;;) {
      SENTENCE_END.lastIndex = 0;
      let cut: RegExpExecArray | null = null;
      for (let m = SENTENCE_END.exec(this.buf); m; m = SENTENCE_END.exec(this.buf)) {
        if (m.index >= this.minChars) {
          cut = m;
          break;
        }
      }
      if (!cut) break;
      out.push(this.buf.slice(0, cut.index).trim());
      this.buf = this.buf.slice(cut.index + cut[0].length);
    }
    return out.filter(Boolean);
  }

  flush(): string[] {
    const rest = this.buf.trim();
    this.buf = "";
    return rest ? [rest] : [];
  }
}

/** Frames of a fixed size from audio chunks of any size. */
export class Framer {
  private pending = new Float32Array(0);
  constructor(readonly size: number) {}

  push(chunk: Float32Array): Float32Array[] {
    const joined = new Float32Array(this.pending.length + chunk.length);
    joined.set(this.pending);
    joined.set(chunk, this.pending.length);
    const frames: Float32Array[] = [];
    let i = 0;
    for (; i + this.size <= joined.length; i += this.size) frames.push(joined.slice(i, i + this.size));
    this.pending = joined.slice(i);
    return frames;
  }
}
