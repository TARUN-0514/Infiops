import { describe, expect, it } from "vitest";
import { describeUserAgent, greetingFor } from "./utils";

describe("greetingFor", () => {
  it("uses the user's time zone, not the machine's", () => {
    const utcMidnight = new Date("2026-11-21T03:00:00Z"); // 08:30 in Kolkata, 19:00 in Los Angeles
    expect(greetingFor(utcMidnight, "Asia/Kolkata")).toBe("Good morning");
    expect(greetingFor(utcMidnight, "America/Los_Angeles")).toBe("Good evening");
  });

  it("covers each part of the day", () => {
    const at = (h: number) => new Date(Date.UTC(2026, 10, 21, h));
    expect(greetingFor(at(2), "UTC")).toBe("Good night");
    expect(greetingFor(at(9), "UTC")).toBe("Good morning");
    expect(greetingFor(at(14), "UTC")).toBe("Good afternoon");
    expect(greetingFor(at(20), "UTC")).toBe("Good evening");
  });
});

describe("describeUserAgent", () => {
  it("names common browsers and systems", () => {
    expect(describeUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36")).toBe("Chrome on Windows");
    expect(describeUserAgent("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36")).toBe("Chrome on Android");
    expect(describeUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1")).toBe("Safari on iOS");
    expect(describeUserAgent(null)).toBe("Unknown device");
  });
});
