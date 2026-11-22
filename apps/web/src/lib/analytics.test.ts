import { describe, expect, it } from "vitest";
import { bucketLabel, goalStatus, hours, loadScore, parseRange, rateLabel, rateTone, severityTone } from "./analytics";

describe("analytics helpers", () => {
  it("never shows a made-up rate", () => {
    expect(rateLabel(null)).toBe("–");
    expect(rateLabel(67)).toBe("67%");
    expect(rateTone(null)).toBeUndefined();
    expect([rateTone(80), rateTone(60), rateTone(10)]).toEqual(["good", "warn", "danger"]);
  });
  it("parses the range from the URL", () => {
    expect([parseRange("7"), parseRange("90"), parseRange("14"), parseRange(null)]).toEqual([7, 90, 30, 30]);
  });
  it("formats minutes as hours", () => {
    expect(hours(45)).toBe("45 min");
    expect(hours(90)).toBe("1.5 h");
    expect(hours(725)).toBe("12 h");
  });
  it("labels buckets and severities", () => {
    expect(bucketLabel("2026-11-02")).toBe("2 Nov");
    expect(severityTone("high")).toBe("danger");
    expect(severityTone("low")).toBe("muted");
  });
  it("scores a day's load and describes goals", () => {
    expect(loadScore({ day: "2026-11-22", meeting_minutes: 120, tasks_due: 3, free_minutes: 0, conflicts: 0, overloaded: false, reasons: [] })).toBe(5);
    expect(goalStatus({ progress: 100, expected: 40, behind: false })).toBe("Done");
    expect(goalStatus({ progress: 10, expected: null, behind: false })).toBe("No target date");
    expect(goalStatus({ progress: 10, expected: 50, behind: true })).toBe("Behind (expected 50%)");
    expect(goalStatus({ progress: 45, expected: 50, behind: false })).toBe("On track");
  });
});
