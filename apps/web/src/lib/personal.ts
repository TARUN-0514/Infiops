// Personal life: goals, routines, lists, journal and important dates.

export type Milestone = { title: string; done: boolean };
export type Goal = { id: string; title: string; area: string; why: string | null; target_date: string | null; days_left: number | null; status: "active" | "done" | "dropped"; progress: number; milestones: Milestone[] };
export type Routine = { id: string; name: string; time_of_day: "morning" | "afternoon" | "evening" | "any"; steps: string[]; weekdays: number[]; active: boolean; due_today: boolean; done_steps: number[]; completed_days: number; due_days: number };
export type ListItem = { id: string; text: string; note: string | null; done: boolean; position: number };
export type PersonalList = { id: string; name: string; kind: "checklist" | "shopping" | "reading" | "travel" | "ideas"; archived: boolean; items: ListItem[] };
export type JournalEntry = { id: string; day: string; mood: number | null; content: string; tags: string[]; created_at: string };
export type JournalMonth = { month: string; entries: JournalEntry[]; days_written: number; average_mood: number | null };
export type ImportantDate = { id: string; title: string; kind: "birthday" | "anniversary" | "renewal" | "deadline" | "other"; month: number; day: number; year: number | null; yearly: boolean; remind_days: number; notes: string | null; next: string | null; days_left: number | null; turning: number | null };

export const AREAS = ["personal", "career", "health", "money", "learning", "relationships"] as const;
// Monday first, matching Python's weekday() numbers 0 to 6.
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const MOODS = ["", "Low", "Meh", "OK", "Good", "Great"];
export const LIST_KINDS = ["checklist", "shopping", "reading", "travel", "ideas"] as const;
export const DATE_KINDS = ["birthday", "anniversary", "renewal", "deadline", "other"] as const;

export function weekdaysLabel(days: number[]): string {
  if (!days.length || days.length === 7) return "Every day";
  const s = [...days].sort((a, b) => a - b);
  if (s.join() === "0,1,2,3,4") return "Weekdays";
  if (s.join() === "5,6") return "Weekends";
  return s.map((d) => WEEKDAYS[d]).join(", ");
}

/** Progress from milestones when there are any, else the manual percent. Mirrors the API. */
export function goalProgress(milestones: Milestone[], manual: number): number {
  return milestones.length ? Math.round((100 * milestones.filter((m) => m.done).length) / milestones.length) : manual;
}

export function whenLabel(daysLeft: number | null): string {
  if (daysLeft === null) return "Passed";
  if (daysLeft === 0) return "Today";
  if (daysLeft === 1) return "Tomorrow";
  if (daysLeft < 0) return `${-daysLeft} days ago`;
  if (daysLeft < 7) return `In ${daysLeft} days`;
  if (daysLeft < 60) return `In ${Math.round(daysLeft / 7)} week${Math.round(daysLeft / 7) === 1 ? "" : "s"}`;
  return `In ${Math.round(daysLeft / 30)} months`;
}

/** "Turning 61", "12th anniversary", or "" when the year isn't known. */
export function occasion(d: Pick<ImportantDate, "kind" | "turning">): string {
  if (!d.turning) return "";
  if (d.kind === "birthday") return `Turning ${d.turning}`;
  if (d.kind === "anniversary") return `${ordinal(d.turning)} anniversary`;
  return "";
}

export function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}

export function parseTags(raw: string): string[] {
  const seen = new Set<string>();
  return raw.split(/[,#\s]+/).map((t) => t.trim().toLowerCase().slice(0, 30)).filter((t) => t && !seen.has(t) && seen.add(t)).slice(0, 10);
}

export function daysInMonth(month: number): number {
  return [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 31;
}
