import { describe, expect, it } from "vitest";
import { describeRecurrence, formatBytes, formatDue, fromLocalInput, speakable, toLocalInput } from "./format";

const TZ = "Asia/Kolkata";
const NOW = new Date("2026-11-21T04:30:00Z"); // 10:00 IST, Saturday

describe("formatDue", () => {
  it("labels today and tomorrow in the user's zone", () => {
    expect(formatDue({ due_at: "2026-11-21T12:30:00Z", all_day: false }, TZ, NOW)).toEqual({ label: "Today, 18:00", overdue: false });
    expect(formatDue({ due_at: "2026-11-22T03:30:00Z", all_day: true }, TZ, NOW)).toEqual({ label: "Tomorrow", overdue: false });
  });
  it("marks overdue", () => {
    expect(formatDue({ due_at: "2026-11-20T03:30:00Z", all_day: true }, TZ, NOW)?.overdue).toBe(true);
    expect(formatDue({ due_at: null, all_day: false }, TZ, NOW)).toBeNull();
  });
});

describe("describeRecurrence", () => {
  it("reads the common rules", () => {
    expect(describeRecurrence("FREQ=DAILY")).toBe("Every day");
    expect(describeRecurrence("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")).toBe("Every weekday");
    expect(describeRecurrence("FREQ=WEEKLY;BYDAY=MO,WE")).toBe("Every Mon, Wed");
    expect(describeRecurrence("FREQ=MONTHLY;BYMONTHDAY=1")).toBe("Monthly on day 1");
    expect(describeRecurrence(null)).toBeNull();
  });
});

describe("local datetime input", () => {
  it("round-trips through the user's time zone", () => {
    const iso = "2026-11-22T12:30:00.000Z";
    expect(toLocalInput(iso, TZ)).toBe("2026-11-22T18:00");
    expect(fromLocalInput("2026-11-22T18:00", TZ)).toBe(iso);
    expect(fromLocalInput("", TZ)).toBeNull();
  });
});

describe("speakable", () => {
  it("turns markdown into sentences", () => {
    expect(speakable("## Schedule\n- **10:00** Standup\n- Lunch [1]\n\nThat's it.")).toBe("Schedule. 10:00 Standup. Lunch. That's it.");
  });
});

describe("formatBytes", () => {
  it("picks a unit", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});
