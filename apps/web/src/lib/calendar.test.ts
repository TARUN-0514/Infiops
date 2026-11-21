import { describe, expect, it } from "vitest";
import { addDays, dayKey, fromLocalInputValue, layoutDay, monthGrid, overlapsDay, toLocalInputValue, weekDays, zonedTime } from "./calendar";

const IST = "Asia/Kolkata";

describe("calendar maths", () => {
  it("finds local midnight in a zone", () => {
    expect(zonedTime("2026-11-23", IST).toISOString()).toBe("2026-11-22T18:30:00.000Z");
    expect(zonedTime("2026-11-23", IST, 9, 30).toISOString()).toBe("2026-11-23T04:00:00.000Z");
    // New York switches from EDT to EST on 2026-11-01
    expect(zonedTime("2026-11-02", "America/New_York").toISOString()).toBe("2026-11-02T05:00:00.000Z");
    expect(zonedTime("2026-10-30", "America/New_York").toISOString()).toBe("2026-10-30T04:00:00.000Z");
  });

  it("keys days in the owner's zone", () => {
    expect(dayKey(new Date("2026-11-22T20:00:00Z"), IST)).toBe("2026-11-23");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("builds Monday-first weeks and month grids", () => {
    expect(weekDays("2026-11-26")[0]).toBe("2026-11-23");
    const grid = monthGrid("2026-11-15");
    expect(grid).toHaveLength(42);
    expect(grid[0]).toBe("2026-10-26");
    expect(grid).toContain("2026-11-30");
  });

  it("places overlapping events side by side", () => {
    const at = (h: number, m = 0) => zonedTime("2026-11-23", IST, h, m).toISOString();
    const events = [
      { id: "a", starts_at: at(10), ends_at: at(11), all_day: false },
      { id: "b", starts_at: at(10, 30), ends_at: at(11, 30), all_day: false },
      { id: "c", starts_at: at(14), ends_at: at(15), all_day: false },
    ];
    const placed = layoutDay(events, "2026-11-23", IST);
    const byId = Object.fromEntries(placed.map((p) => [p.event.id, p]));
    expect(byId.a.cols).toBe(2);
    expect(byId.b.col).toBe(1);
    expect(byId.c.cols).toBe(1);
    expect(byId.a.top).toBeCloseTo(10 / 24);
    expect(byId.c.height).toBeCloseTo(1 / 24);
  });

  it("treats all-day events as covering their day only", () => {
    const e = { id: "x", starts_at: zonedTime("2026-11-23", IST).toISOString(), ends_at: zonedTime("2026-11-24", IST).toISOString(), all_day: true };
    expect(overlapsDay(e, "2026-11-23", IST)).toBe(true);
    expect(overlapsDay(e, "2026-11-24", IST)).toBe(false);
  });

  it("round-trips datetime-local values", () => {
    const iso = "2026-11-23T04:00:00.000Z";
    expect(toLocalInputValue(iso, IST)).toBe("2026-11-23T09:30");
    expect(fromLocalInputValue("2026-11-23T09:30", IST).toISOString()).toBe(iso);
  });
});
