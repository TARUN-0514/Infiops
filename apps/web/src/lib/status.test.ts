import { describe, expect, it } from "vitest";
import { bannerProblems, bannerText, jobName, jobsOf, overallLabel, sortChecks, stateLabel, type StatusCheck, type SystemStatus } from "./status";

const check = (key: string, state: StatusCheck["state"], label = key): StatusCheck => ({ key, label, state, detail: `${label} detail.` });
const status = (...checks: StatusCheck[]): SystemStatus => ({ overall: "ok", checked_at: "2026-11-22T10:00:00Z", checks });

describe("system status helpers", () => {
  it("puts problems first", () => {
    const sorted = sortChecks([check("a", "off"), check("b", "ok"), check("c", "error"), check("d", "warn")]);
    expect(sorted.map((c) => c.key)).toEqual(["c", "d", "b", "a"]);
  });
  it("labels states and the overall picture in plain words", () => {
    expect(stateLabel("off")).toBe("Not set up");
    expect(overallLabel(status(check("a", "ok"), check("b", "off")))).toBe("Everything is working");
    expect(overallLabel(status(check("a", "warn")))).toBe("1 thing needs a look");
    expect(overallLabel(status(check("a", "error"), check("b", "error"), check("c", "warn")))).toBe("2 things aren't working");
  });
  it("shows the banner only for things that are broken", () => {
    expect(bannerProblems(undefined)).toEqual({ problems: [], signature: "" });
    const s = status(check("worker", "error", "Background worker"), check("backups", "warn"), check("model", "error", "Local AI model"));
    const { problems, signature } = bannerProblems(s);
    expect(problems.map((p) => p.key)).toEqual(["worker", "model"]);
    expect(signature).toBe("model,worker");
    expect(bannerText(problems)).toBe("Background worker and 1 more aren't working.");
    expect(bannerText(problems.slice(0, 1))).toBe("Background worker isn't working. Background worker detail.");
  });
  it("names scheduled jobs", () => {
    const c: StatusCheck = { ...check("jobs", "ok"), jobs: { sync_all: { last_run: "x", last_ok: "x", error: null, failures: 0, ms: 4 }, briefing_tick: { last_run: "x", last_ok: null, error: "boom", failures: 2, ms: 0 } } };
    expect(jobsOf(c).map(([k]) => k)).toEqual(["briefing_tick", "sync_all"]);
    expect(jobName("sync_all")).toBe("Email and calendar sync");
    expect(jobName("new_job")).toBe("new job");
  });
});
