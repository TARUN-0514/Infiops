import { describe, expect, it } from "vitest";
import { availableRefs, blankStep, describeTrigger, draftProblem, inputKind, moveStep, stepSummary, statusTone, type WorkflowDraft } from "./automation";

const base: WorkflowDraft = { name: "Morning", description: null, trigger: { type: "manual" }, steps: [blankStep("notify")], enabled: true };

describe("automation helpers", () => {
  it("describes triggers like the API", () => {
    expect(describeTrigger({ type: "schedule", every: "day", at: "08:00", weekdays: [4, 0, 1, 2, 3] })).toBe("Weekdays at 08:00");
    expect(describeTrigger({ type: "schedule", every: "day", at: "07:30", weekdays: [] })).toBe("Every day at 07:30");
    expect(describeTrigger({ type: "schedule", every: "day", at: "07:30", weekdays: [5, 6] })).toBe("Sat, Sun at 07:30");
    expect(describeTrigger({ type: "schedule", every: "month", day: 1, at: "09:00" })).toBe("Monthly on day 1 at 09:00");
    expect(describeTrigger({ type: "schedule", every: "hours", hours: 1 })).toBe("Every 1 hour");
    expect(describeTrigger({ type: "event", event: "task.created", filter: {} }, () => "A task is created")).toBe("A task is created");
  });

  it("finds the first problem", () => {
    expect(draftProblem({ ...base, steps: [{ ...blankStep("notify"), config: { title: "Hi" } }] })).toBeNull();
    expect(draftProblem({ ...base, name: " " })).toBe("Give it a name.");
    expect(draftProblem(base)).toBe("Step 1: give the notification a title.");
    expect(draftProblem({ ...base, steps: [] })).toBe("Add at least one step.");
    expect(draftProblem({ ...base, trigger: { type: "schedule", every: "month", at: "09:00" }, steps: [{ ...blankStep("approval"), config: { message: "ok" } }] })).toBe("Pick a day of the month.");
    expect(draftProblem({ ...base, steps: [{ ...blankStep("condition"), config: { left: "x", op: "equals", right: "" } }] })).toBe("Step 1: say what to compare with.");
  });

  it("moves steps", () => {
    expect(moveStep(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(moveStep(["a", "b"], 0, -1)).toEqual(["a", "b"]);
  });

  it("offers earlier results only", () => {
    const steps = [{ ...blankStep("tool"), config: { tool: "tasks_list", args: {} } }, blankStep("agent"), blankStep("notify")];
    const refs = availableRefs(steps, 2, { type: "event", event: "task.created", filter: {} }, { events: [{ name: "task.created", label: "", fields: ["title"] }], condition_ops: [], tools: [], timezone: "UTC" });
    expect(refs.map((r) => r.value)).toEqual(["{{now.date}}", "{{trigger.title}}", "{{steps.1.output}}", "{{steps.2.output.text}}"]);
    expect(availableRefs(steps, 0, { type: "manual" }).length).toBe(1);
  });

  it("maps tool inputs to fields", () => {
    expect(inputKind({ type: "string" })).toBe("text");
    expect(inputKind({ enum: ["a"] })).toBe("select");
    expect(inputKind({ anyOf: [{ type: "integer" }, { type: "null" }] })).toBe("number");
    expect(inputKind({ type: "boolean" })).toBe("boolean");
    expect(inputKind({ type: "array" })).toBe("json");
  });

  it("summarises steps and tones", () => {
    expect(stepSummary({ ...blankStep("condition"), config: { left: "{{steps.1.output}}", op: "not_empty" } })).toBe("{{steps.1.output}} is not empty");
    expect(stepSummary({ ...blankStep("tool"), name: "Make a task" })).toBe("Make a task");
    expect(statusTone("failed")).toBe("danger");
    expect(statusTone("waiting_approval")).toBe("warn");
  });
});
