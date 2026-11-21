// Fitness types and pure helpers. Numbers arrive as decimal strings.

export type Metric = "weight_kg" | "body_fat_pct" | "waist_cm" | "calories" | "protein_g" | "water_ml" | "sleep_hours";
export type MetricSpec = { label: string; unit: string; min: number; max: number; sum: boolean };
export type WorkoutSet = { exercise: string; reps: number | null; weight_kg: string | null; seconds: number | null; distance_km: string | null };
export type Workout = { id: string; day: string; title: string; minutes: number | null; notes: string | null; volume_kg: string; sets: WorkoutSet[] };
export type Exercise = { id?: string; name: string; muscle: string; equipment: string; custom: boolean };
export type Best = { weight_kg: string; reps: number | null; day: string };
export type LogEntry = { id: string; day: string; metric: Metric; value: string; note: string | null };
export type Logs = { start: string; end: string; entries: LogEntry[]; daily: Partial<Record<Metric, { day: string; value: string }[]>> };
export type Habit = { id: string; name: string; per_week: number; archived: boolean; days: string[]; streak: number; this_week: number };
export type HabitList = { today: string; start: string; habits: Habit[] };
export type WeekFacts = {
  workouts: number;
  minutes: number;
  sets: number;
  volume_kg: string;
  avg: Record<"calories" | "protein_g" | "water_ml" | "sleep_hours", string | null>;
  days_logged: Record<Metric, number>;
  weight_start: string | null;
  weight_end: string | null;
};
export type WeekReport = { week_start: string; week_end: string; this_week: WeekFacts; last_week: WeekFacts; habits: { name: string; done: number; target: number }[]; note: string };
export type TrackingDay = { day: string; future: boolean; spending: number; workouts: number; logs: number };
export type TrackingMonth = { month: string; days: TrackingDay[]; days_so_far: number; spending_days: number; workout_days: number; tracked_days: number };

/** A set the form is editing: strings so inputs can be empty. */
export type SetDraft = { exercise: string; reps: string; weight_kg: string; seconds: string; distance_km: string };

export const emptySet = (exercise = ""): SetDraft => ({ exercise, reps: "", weight_kg: "", seconds: "", distance_km: "" });

/** Convert form rows to the API shape; returns an error message when a row is incomplete. */
export function toSets(drafts: SetDraft[]): { sets: WorkoutSet[]; error: string | null } {
  const sets: WorkoutSet[] = [];
  for (const [i, d] of drafts.entries()) {
    const blank = !d.exercise.trim() && !d.reps && !d.weight_kg && !d.seconds && !d.distance_km;
    if (blank) continue;
    if (!d.exercise.trim()) return { sets: [], error: `Set ${i + 1} needs an exercise.` };
    const reps = d.reps ? Number(d.reps) : null;
    const seconds = d.seconds ? Math.round(Number(d.seconds) * 60) : null; // form takes minutes
    if (!reps && !seconds && !Number(d.distance_km)) return { sets: [], error: `Set ${i + 1} needs reps, time or distance.` };
    sets.push({ exercise: d.exercise.trim(), reps, weight_kg: d.weight_kg || null, seconds, distance_km: d.distance_km || null });
  }
  if (!sets.length) return { sets: [], error: "Add at least one set." };
  return { sets, error: null };
}

export function volume(sets: Pick<WorkoutSet, "reps" | "weight_kg">[]): number {
  return sets.reduce((n, s) => n + (s.reps ?? 0) * Number(s.weight_kg ?? 0), 0);
}

/** "3 × 8 @ 60 kg" style summary of one exercise's sets in a workout. */
export function summarise(sets: WorkoutSet[]): { exercise: string; text: string }[] {
  const groups = new Map<string, WorkoutSet[]>();
  for (const s of sets) groups.set(s.exercise, [...(groups.get(s.exercise) ?? []), s]);
  return [...groups.entries()].map(([exercise, list]) => ({
    exercise,
    text: list
      .map((s) => {
        if (s.reps) return s.weight_kg ? `${s.reps} × ${num(s.weight_kg)} kg` : `${s.reps} reps`;
        const parts = [s.seconds ? `${Math.round(s.seconds / 60)} min` : "", s.distance_km ? `${num(s.distance_km)} km` : ""];
        return parts.filter(Boolean).join(", ");
      })
      .join(" · "),
  }));
}

export function num(v: string | number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || v === "") return "–";
  const n = Number(v);
  return Number.isFinite(n) ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits }).format(n) : "–";
}

/** Change between two weeks, as text and a direction; null when either side is missing. */
export function delta(now: string | number | null, before: string | number | null): { text: string; dir: "up" | "down" | "same" } | null {
  if (now === null || before === null || now === "" || before === "") return null;
  const d = Number(now) - Number(before);
  if (!Number.isFinite(d)) return null;
  if (Math.abs(d) < 0.05) return { text: "same", dir: "same" };
  return { text: `${d > 0 ? "+" : "−"}${num(Math.abs(d))}`, dir: d > 0 ? "up" : "down" };
}

/** The last n days ending at `today`, oldest first, as YYYY-MM-DD. */
export function lastDays(today: string, n: number): string[] {
  const end = new Date(`${today}T00:00:00Z`).getTime();
  return Array.from({ length: n }, (_, i) => new Date(end - (n - 1 - i) * 86_400_000).toISOString().slice(0, 10));
}

/** Monday-first grid of a month: leading blanks then each day. */
export function monthGrid(days: TrackingDay[]): (TrackingDay | null)[] {
  if (!days.length) return [];
  const first = new Date(`${days[0].day}T00:00:00Z`).getUTCDay(); // 0 = Sunday
  const lead = (first + 6) % 7;
  return [...Array<null>(lead).fill(null), ...days];
}
