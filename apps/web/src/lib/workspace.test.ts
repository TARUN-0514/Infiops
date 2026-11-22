import { describe, expect, it } from "vitest";
import { byStatus, bySection, fieldKey, hours, nextStatus, parseStatuses, severityShare, slaLabel, slaTone, type Item, type Topic } from "./workspace";

const ws = { statuses: ["New", "Triaged", "Fixed", "False positive"], closed: ["Fixed", "False positive"] };

describe("workspace helpers", () => {
  it("labels SLA state", () => {
    expect(slaLabel({ days_left: -1, closed: false })).toBe("1 day over SLA");
    expect(slaLabel({ days_left: -4, closed: false })).toBe("4 days over SLA");
    expect(slaLabel({ days_left: 0, closed: false })).toBe("Due today");
    expect(slaLabel({ days_left: 1, closed: false })).toBe("1 day left");
    expect(slaLabel({ days_left: 3, closed: true })).toBe("");
    expect(slaLabel({ days_left: null, closed: false })).toBe("");
    expect(slaTone({ days_left: -1, closed: false })).toBe("danger");
    expect(slaTone({ days_left: 5, closed: false })).toBe("warn");
    expect(slaTone({ days_left: 30, closed: false })).toBe("muted");
  });

  it("groups by status in board order", () => {
    const items = [{ status: "Triaged" }, { status: "New" }, { status: "Odd" }] as Item[];
    const g = byStatus(ws, items);
    expect(g.map(([s, xs]) => [s, xs.length])).toEqual([["New", 1], ["Triaged", 1], ["Fixed", 0], ["False positive", 0], ["Odd", 1]]);
  });

  it("finds the next open status", () => {
    expect(nextStatus(ws, "New")).toBe("Triaged");
    expect(nextStatus(ws, "Triaged")).toBe("Fixed");
    expect(nextStatus(ws, "False positive")).toBeNull();
    expect(nextStatus(ws, "Gone")).toBeNull();
  });

  it("splits severities", () => {
    const s = severityShare({ open: 4, by_severity: { critical: 1, high: 3, medium: 0, low: 0, info: 0 } });
    expect(s).toEqual([{ severity: "critical", n: 1, pct: 25 }, { severity: "high", n: 3, pct: 75 }]);
    expect(severityShare({ open: 0, by_severity: { critical: 0, high: 0, medium: 0, low: 0, info: 0 } })).toEqual([]);
  });

  it("parses board settings", () => {
    expect(parseStatuses(" Plan, Run ,, run, Done ")).toEqual(["Plan", "Run", "Done"]);
    expect(fieldKey("Test window")).toBe("test_window");
    expect(fieldKey("2nd owner")).toBe("f_2nd_owner");
  });

  it("formats study time and sections", () => {
    expect(hours(90)).toBe("1h 30m");
    expect(hours(120)).toBe("2h");
    expect(hours(45)).toBe("45m");
    const t = [{ section: "Web", title: "SQLi" }, { section: "", title: "x" }, { section: "Web", title: "XSS" }] as Topic[];
    expect(bySection(t).map(([s, xs]) => [s, xs.length])).toEqual([["Web", 2], ["Other", 1]]);
  });
});
