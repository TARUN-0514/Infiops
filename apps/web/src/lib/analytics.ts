// Types and pure helpers for the Analytics page and the insight cards.

export type Severity = "high" | "medium" | "low";
export type InsightKind = "overdue" | "unanswered" | "conflicts" | "overloaded" | "postponed";

export type Insight = {
  kind: InsightKind;
  severity: Severity;
  title: string;
  detail: string;
  link: string;
  count: number;
  items: { id: string; label: string; sub: string; link: string }[];
};

export type InsightsResponse = { insights: Insight[]; rules: Record<string, number> };

export type DayLoad = {
  day: string;
  meeting_minutes: number;
  tasks_due: number;
  free_minutes: number;
  conflicts: number;
  overloaded: boolean;
  reasons: string[];
};

export type Analytics = {
  range: { days: number; from: string; to: string; bucket: "day" | "week" };
  tasks: {
    series: { bucket: string; created: number; completed: number }[];
    created: number;
    completed: number;
    completion_rate: number | null;
    on_time_rate: number | null;
    with_due: number;
    open: number;
    overdue: number;
    by_project: { project: string; completed: number }[];
    postponed: { id: string; title: string; times: number }[];
  };
  time: {
    categories: { label: string; group: string; minutes: number }[];
    total_minutes: number;
    work_entries_without_minutes: number;
    meetings: { count: number; series: { bucket: string; minutes: number }[] };
  };
  habits: { id: string; name: string; per_week: number; done: number; target: number; rate: number | null; streak: number; tracked_days: number }[];
  goals: { id: string; title: string; area: string; progress: number; expected: number | null; target_date: string | null; days_left: number | null; behind: boolean; milestones: number }[];
  workload: DayLoad[];
  finance: {
    has_data: boolean;
    months: { month: string; income: number; expense: number; net: number }[];
    top_categories: { category: string; spent: number; budget: number | null }[];
    over_budget: string[];
  };
  fitness: {
    workouts: number;
    series: { bucket: string; workouts: number; minutes: number }[];
    weight: { day: string; kg: number }[];
    weight_change: number | null;
    sleep_avg: number | null;
    sleep_days: number;
  };
};

export const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
] as const;
export type RangeDays = (typeof RANGES)[number]["days"];

export function parseRange(raw: string | null): RangeDays {
  const n = Number(raw);
  return n === 7 || n === 90 ? n : 30;
}

/** "–" when there was nothing to measure, so no rate is ever made up. */
export function rateLabel(v: number | null): string {
  return v === null ? "–" : `${v}%`;
}

export function hours(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = minutes / 60;
  return `${h >= 10 ? Math.round(h) : Math.round(h * 10) / 10} h`;
}

const UTC = (key: string) => new Date(`${key}T00:00:00Z`);

/** "2 Nov". A weekly bucket is labelled by its Monday. */
export function bucketLabel(key: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(UTC(key));
}

export function weekdayShort(key: string): string {
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", timeZone: "UTC" }).format(UTC(key));
}

export function severityTone(s: Severity): "danger" | "warn" | "muted" {
  return s === "high" ? "danger" : s === "medium" ? "warn" : "muted";
}

export function rateTone(v: number | null): "good" | "warn" | "danger" | undefined {
  if (v === null) return undefined;
  return v >= 75 ? "good" : v >= 50 ? "warn" : "danger";
}

/** Height of a day's load bar, relative to the busiest day shown (meeting hours plus tasks). */
export function loadScore(d: DayLoad): number {
  return d.meeting_minutes / 60 + d.tasks_due;
}

export function goalStatus(g: { progress: number; expected: number | null; behind: boolean }): string {
  if (g.progress >= 100) return "Done";
  if (g.expected === null) return "No target date";
  return g.behind ? `Behind (expected ${g.expected}%)` : "On track";
}
