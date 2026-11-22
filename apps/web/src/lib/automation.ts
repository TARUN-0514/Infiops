// Automations: types from the API and pure helpers for the builder.

export type StepKind = "tool" | "agent" | "condition" | "approval" | "notify";
export type Trigger =
  | { type: "manual" }
  | { type: "schedule"; every: "day" | "month" | "hours"; at?: string | null; weekdays?: number[]; day?: number | null; hours?: number | null }
  | { type: "event"; event: string; filter: Record<string, string> };
export type Step = { kind: StepKind; name: string; config: Record<string, unknown>; retry_max: number };
export type WorkflowDraft = { name: string; description: string | null; trigger: Trigger; steps: Step[]; enabled: boolean; created_from_prompt?: string | null };
export type Health = { runs: number; failed: number; success_pct: number | null };
export type Workflow = WorkflowDraft & {
  id: string;
  trigger_label: string;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: RunStatus | null;
  health: Health;
  step_count: number;
};
export type RunStatus = "queued" | "running" | "waiting_approval" | "retrying" | "succeeded" | "stopped" | "failed" | "cancelled";
export type RunStep = { ordinal: number; kind: StepKind; name: string; config: Record<string, unknown>; status: string; attempts: number; output?: Record<string, unknown> | null; error?: string | null; approval_id?: string; message?: string; started_at?: string; finished_at?: string };
export type Run = { id: string; workflow_id: string; workflow: string | null; status: RunStatus; trigger: { type: string; event?: string; data?: Record<string, unknown> }; cursor: number; steps: RunStep[]; error: string | null; resume_at: string | null; started_at: string; finished_at: string | null };
export type ToolInfo = { name: string; description: string; risk: string; local_only: boolean; inputs: Record<string, { type?: string; enum?: string[]; description?: string; anyOf?: { type?: string }[]; items?: unknown }>; required: string[] };
export type AutomationMeta = { events: { name: string; label: string; fields: string[] }[]; condition_ops: string[]; tools: ToolInfo[]; timezone: string };

export const KIND_LABEL: Record<StepKind, string> = { tool: "Do something", agent: "Write with AI", condition: "Only if", approval: "Ask me first", notify: "Notify me" };
export const OP_LABEL: Record<string, string> = { equals: "is", not_equals: "is not", contains: "contains", greater_than: "is more than", less_than: "is less than", empty: "is empty", not_empty: "is not empty" };
export const STATUS_LABEL: Record<RunStatus, string> = { queued: "Queued", running: "Running", waiting_approval: "Waiting for you", retrying: "Retrying", succeeded: "Done", stopped: "Stopped", failed: "Failed", cancelled: "Cancelled" };
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function statusTone(s: RunStatus | null): "good" | "danger" | "warn" | "muted" {
  if (s === "succeeded") return "good";
  if (s === "failed") return "danger";
  if (s === "waiting_approval" || s === "retrying") return "warn";
  return "muted";
}

/** Mirrors the API's trigger description. */
export function describeTrigger(t: Trigger, eventLabel?: (name: string) => string | undefined): string {
  if (t.type === "manual") return "When you run it";
  if (t.type === "event") return eventLabel?.(t.event) ?? t.event;
  if (t.every === "hours") return `Every ${t.hours} hour${t.hours === 1 ? "" : "s"}`;
  if (t.every === "month") return `Monthly on day ${t.day} at ${t.at}`;
  const d = [...(t.weekdays ?? [])].sort((a, b) => a - b);
  const when = !d.length || d.length === 7 ? "Every day" : d.join() === "0,1,2,3,4" ? "Weekdays" : d.map((x) => WEEKDAYS[x]).join(", ");
  return `${when} at ${t.at}`;
}

export function blankStep(kind: StepKind): Step {
  const config: Record<StepKind, Record<string, unknown>> = {
    tool: { tool: "", args: {} },
    agent: { prompt: "" },
    condition: { left: "", op: "not_empty", right: "" },
    approval: { message: "" },
    notify: { title: "", body: "" },
  };
  return { kind, name: "", config: config[kind], retry_max: kind === "tool" || kind === "agent" ? 2 : 0 };
}

export function moveStep<T>(steps: T[], from: number, to: number): T[] {
  if (to < 0 || to >= steps.length || from === to) return steps;
  const out = [...steps];
  const [s] = out.splice(from, 1);
  out.splice(to, 0, s);
  return out;
}

/** Values a step can use: the trigger's fields and earlier steps' outputs. */
export function availableRefs(steps: Step[], index: number, trigger: Trigger, meta?: AutomationMeta): { label: string; value: string }[] {
  const refs: { label: string; value: string }[] = [{ label: "Today's date", value: "{{now.date}}" }];
  if (trigger.type === "event") {
    const ev = meta?.events.find((e) => e.name === trigger.event);
    for (const f of ev?.fields ?? []) refs.push({ label: `Trigger: ${f}`, value: `{{trigger.${f}}}` });
  }
  steps.slice(0, index).forEach((s, i) => {
    const n = i + 1;
    if (s.kind === "agent") refs.push({ label: `Step ${n}: written text`, value: `{{steps.${n}.output.text}}` });
    else if (s.kind === "tool") refs.push({ label: `Step ${n}: ${String(s.config.tool || "result")}`, value: `{{steps.${n}.output}}` });
  });
  return refs;
}

/** First problem the API would reject, in plain words, or null. */
export function draftProblem(d: WorkflowDraft): string | null {
  if (!d.name.trim()) return "Give it a name.";
  const t = d.trigger;
  if (t.type === "schedule") {
    if (t.every !== "hours" && !t.at) return "Pick a time of day.";
    if (t.every === "month" && !t.day) return "Pick a day of the month.";
    if (t.every === "hours" && !t.hours) return "Pick how many hours apart.";
  }
  if (!d.steps.length) return "Add at least one step.";
  for (const [i, s] of d.steps.entries()) {
    const c = s.config;
    const n = `Step ${i + 1}`;
    if (s.kind === "tool" && !c.tool) return `${n}: pick what to do.`;
    if (s.kind === "agent" && !String(c.prompt ?? "").trim()) return `${n}: say what to write.`;
    if (s.kind === "condition" && !String(c.left ?? "").trim()) return `${n}: pick a value to check.`;
    if (s.kind === "condition" && !["empty", "not_empty"].includes(String(c.op)) && !String(c.right ?? "").trim()) return `${n}: say what to compare with.`;
    if (s.kind === "approval" && !String(c.message ?? "").trim()) return `${n}: say what you're approving.`;
    if (s.kind === "notify" && !String(c.title ?? "").trim()) return `${n}: give the notification a title.`;
  }
  return null;
}

/** The input type the builder should show for a tool input. */
export function inputKind(schema: ToolInfo["inputs"][string]): "text" | "number" | "boolean" | "select" | "json" {
  if (schema.enum) return "select";
  const t = schema.type ?? schema.anyOf?.find((x) => x.type && x.type !== "null")?.type;
  if (t === "integer" || t === "number") return "number";
  if (t === "boolean") return "boolean";
  if (t === "string" || t === undefined) return schema.anyOf?.some((x) => x.type === "array" || x.type === "object") ? "json" : "text";
  return "json";
}

export function stepSummary(s: Step | RunStep): string {
  const c = s.config ?? {};
  if (s.name) return s.name;
  if (s.kind === "tool") return String(c.tool || "Pick an action");
  if (s.kind === "agent") return String(c.prompt || "").slice(0, 80) || "Write text";
  if (s.kind === "condition") return `${String(c.left || "…")} ${OP_LABEL[String(c.op)] ?? c.op} ${String(c.right || "")}`.trim();
  if (s.kind === "approval") return String(c.message || "Wait for my OK");
  return String(c.title || "Send a notification");
}
