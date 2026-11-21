import { describe, expect, it } from "vitest";
import { downsample, encodeWav, Endpointer, Framer, rms, SentenceSplitter } from "./core";

function tone(level: number, n = 1280) {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = level * Math.SQRT2 * Math.sin((2 * Math.PI * 440 * i) / 16000);
  return out;
}
const QUIET = tone(0.002);
const LOUD = tone(0.1);

describe("voice core", () => {
  it("measures level", () => {
    expect(rms(new Float32Array())).toBe(0);
    expect(rms(LOUD)).toBeCloseTo(0.1, 2);
  });

  it("detects start and end of speech", () => {
    const ep = new Endpointer(0.015);
    for (let i = 0; i < 5; i++) expect(ep.feed(QUIET)).toBe("waiting");
    expect(ep.feed(LOUD)).toBe("waiting");
    expect(ep.feed(LOUD)).toBe("speaking");
    for (let i = 0; i < 9; i++) expect(ep.feed(QUIET)).toBe("speaking");
    expect(ep.feed(QUIET)).toBe("done"); // 800 ms quiet
    expect(ep.audio().length).toBeGreaterThan(10 * 1280);
  });

  it("times out when nothing is said", () => {
    const ep = new Endpointer(0.015, 160, 800, 15000, 800);
    const results = Array.from({ length: 10 }, () => ep.feed(QUIET));
    expect(results.at(-1)).toBe("timeout");
  });

  it("downsamples and encodes 16 kHz mono WAV", () => {
    const at48 = tone(0.1, 4800);
    const at16 = downsample(at48, 48000);
    expect(at16.length).toBe(1600);
    const wav = new DataView(encodeWav(at16));
    expect(String.fromCharCode(wav.getUint8(0), wav.getUint8(1), wav.getUint8(2), wav.getUint8(3))).toBe("RIFF");
    expect(wav.getUint32(24, true)).toBe(16000);
    expect(wav.getUint32(40, true)).toBe(3200);
  });

  it("splits streamed text into sentences", () => {
    const sp = new SentenceSplitter();
    const got: string[] = [];
    for (const c of ["You have two ", "meetings today. The first is", " at 10. ", "Then lunch", "!"]) got.push(...sp.feed(c));
    expect(got).toEqual(["You have two meetings today.", "The first is at 10."]);
    expect(sp.flush()).toEqual(["Then lunch!"]);
    expect(new SentenceSplitter().feed("Yes. Done. I moved it to Friday at 3. Anything else?")).toEqual(["Yes. Done. I moved it to Friday at 3."]);
  });

  it("frames uneven chunks", () => {
    const f = new Framer(4);
    expect(f.push(new Float32Array(3))).toHaveLength(0);
    expect(f.push(new Float32Array(6))).toHaveLength(2);
    expect(f.push(new Float32Array(3))).toHaveLength(1);
  });
});
