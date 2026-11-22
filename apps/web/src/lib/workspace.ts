// Security workspaces and learning tracks: types from the API and pure helpers.

export const SEVERITIES = ["critical", "high", "medium", "low", "info"] as const;
export type Severity = (typeof SEVERITIES)[number];
export const SOURCES = ["inspector", "ghas", "dast", "guardium", "pentest", "manual"] as const;
export const SOURCE_LABEL: Record<string, string> = {
  inspector: "AWS Inspector",
  ghas: "GitHub Advanced Security",
  dast: "DAST",
  guardium: "Guardium",
  pentest: "Pentest",
  manual: "Added by hand",
};

export type FieldDef = { key: string; label: string; type: "text" | "number" | "select" | "date"; options?: string[] };

export type Workspace = {
  id: string;
  kind: "vulns" | "appsec" | "cloud" | "pentest" | "custom";
  name: string;
  statuses: string[];
  closed: string[];
  fields: FieldDef[];
  sla_days: Partial<Record<Severity, number>>;
  open: number;
  breached: number;
};

export type Item = {
  id: string;
  workspace_id: string;
  title: string;
  status: string;
  closed: boolean;
  severity: Severity;
  source: string;
  asset: string | null;
  identifier: string | null;
  owner: string | null;
  description: string | null;
  found_on: string;
  due_on: string | null;
  closed_on: string | null;
  follow_up_on: string | null;
  escalated_at: string | null;
  escalated_to: string | null;
  age_days: number;
  days_left: number | null;
  breached: boolean;
  data: Record<string, string | number>;
};

export type ItemEvent = { kind: string; text: string; at: string };
export type ItemDetail = Item & { events: ItemEvent[] };

export type Summary = {
  open: number;
  closed: number;
  by_severity: Record<Severity, number>;
  by_source: Record<string, number>;
  by_status: Record<string, number>;
  aging: Record<"0-30" | "31-60" | "61-90" | "90+", number>;
  breached: number;
  due_soon: number;
  escalated: number;
  mean_days_to_close: number | null;
  closed_in_sla_pct: number | null;
};

export type ImportPreview = {
  rows: number;
  open: number;
  by_severity: Record<Severity, number>;
  sample: { title: string; severity: Severity; asset: string | null; identifier: string | null; found_on: string; fixed: boolean }[];
  errors: string[];
};
export type ImportResult = { added: number; updated: number; unchanged: number; errors: string[] };

export type Topic = { id: string; section: string; title: string; status: "todo" | "learning" | "done"; confidence: number; notes: string | null; next_review_on: string | null; due: boolean; reviews: number };
export type StudySession = { id: string; day: string; kind: "study" | "lab" | "review" | "exam"; minutes: number; topic_id: string | null; topic: string | null; machine: string | null; outcome: "user" | "root" | "stuck" | "partial" | null; notes: string | null };
export type Track = {
  id: string;
  name: string;
  goal: string | null;
  target_date: string | null;
  days_left: number | null;
  topics: Topic[];
  sessions: StudySession[];
  stats: { topics: number; done: number; learning: number; due_reviews: number; hours_total: number; hours_week: number; labs: number; rooted: number };
};

export const SEVERITY_TONE: Record<Severity, string> = {
  critical: "bg-danger/15 text-danger",
  high: "bg-warn/15 text-warn",
  medium: "bg-accent/15 text-accent",
  low: "bg-raised text-muted",
  info: "bg-raised text-muted",
};

/** "3 days over SLA", "Due today", "12 days left", or "" when there's no SLA or it's closed. */
export function slaLabel(it: Pick<Item, "days_left" | "closed">): string {
  if (it.closed || it.days_left === null) return "";
  if (it.days_left < 0) return `${-it.days_left} day${it.days_left === -1 ? "" : "s"} over SLA`;
  if (it.days_left === 0) return "Due today";
  return `${it.days_left} day${it.days_left === 1 ? "" : "s"} left`;
}

export function slaTone(it: Pick<Item, "days_left" | "closed">): "danger" | "warn" | "muted" {
  if (it.closed || it.days_left === null) return "muted";
  if (it.days_left < 0) return "danger";
  return it.days_left <= 7 ? "warn" : "muted";
}

/** Items grouped by status, in the board's own status order. Unknown statuses go last. */
export function byStatus(ws: Pick<Workspace, "statuses">, items: Item[]): [string, Item[]][] {
  const groups = new Map<string, Item[]>(ws.statuses.map((s) => [s, []]));
  for (const it of items) groups.set(it.status, [...(groups.get(it.status) ?? []), it]);
  return [...groups.entries()];
}

/** A status the item can move to next, skipping closed ones, or null at the end. */
export function nextStatus(ws: Pick<Workspace, "statuses" | "closed">, status: string): string | null {
  const i = ws.statuses.indexOf(status);
  if (i < 0) return null;
  const rest = ws.statuses.slice(i + 1);
  return rest.find((s) => !ws.closed.includes(s)) ?? rest[0] ?? null;
}

/** Percent of the summary's open items in each severity, for the stacked bar. */
export function severityShare(s: Pick<Summary, "by_severity" | "open">): { severity: Severity; pct: number; n: number }[] {
  return SEVERITIES.filter((k) => s.by_severity[k] > 0).map((k) => ({ severity: k, n: s.by_severity[k], pct: s.open ? (100 * s.by_severity[k]) / s.open : 0 }));
}

/** Parses the board editor's comma-separated statuses; trims, drops blanks and repeats. */
export function parseStatuses(raw: string): string[] {
  const seen = new Set<string>();
  return raw.split(",").map((s) => s.trim()).filter((s) => s && !seen.has(s.toLowerCase()) && seen.add(s.toLowerCase()));
}

export function fieldKey(label: string): string {
  const k = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 30);
  return /^[a-z]/.test(k) ? k : `f_${k}`.slice(0, 30);
}

export function hours(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
}

/** Topics grouped by syllabus section, keeping their order. */
export function bySection(topics: Topic[]): [string, Topic[]][] {
  const out = new Map<string, Topic[]>();
  for (const t of topics) out.set(t.section || "Other", [...(out.get(t.section || "Other") ?? []), t]);
  return [...out.entries()];
}
