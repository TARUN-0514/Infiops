/** Calendar maths in the owner's time zone. Days are "YYYY-MM-DD" keys. */

type Timed = { id: string; starts_at: string; ends_at: string; all_day: boolean };

function parts(date: Date, tz: string) {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (t: string) => Number(p.find((x) => x.type === t)?.value ?? 0);
  return { y: get("year"), m: get("month"), d: get("day"), h: get("hour"), min: get("minute"), s: get("second") };
}

/** Minutes the zone is ahead of UTC at this instant (IST = 330). */
export function tzOffsetMinutes(date: Date, tz: string): number {
  const p = parts(date, tz);
  const asUtc = Date.UTC(p.y, p.m - 1, p.d, p.h, p.min, p.s);
  return Math.round((asUtc - Math.floor(date.getTime() / 1000) * 1000) / 60000);
}

export function dayKey(date: Date, tz: string): string {
  const p = parts(date, tz);
  return `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`;
}

/** The instant a local wall-clock time happens in tz. */
export function zonedTime(key: string, tz: string, hour = 0, minute = 0): Date {
  const [y, m, d] = key.split("-").map(Number);
  const guess = Date.UTC(y, m - 1, d, hour, minute);
  const first = guess - tzOffsetMinutes(new Date(guess), tz) * 60000;
  // second pass handles days where the offset changes (DST)
  return new Date(guess - tzOffsetMinutes(new Date(first), tz) * 60000);
}

export function addDays(key: string, n: number): string {
  const [y, m, d] = key.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return t.toISOString().slice(0, 10);
}

/** 0 = Monday ... 6 = Sunday */
export function weekdayIndex(key: string): number {
  const [y, m, d] = key.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

export function weekDays(key: string): string[] {
  const monday = addDays(key, -weekdayIndex(key));
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

/** Six Monday-first weeks covering the month that contains key. */
export function monthGrid(key: string): string[] {
  const first = `${key.slice(0, 7)}-01`;
  const start = addDays(first, -weekdayIndex(first));
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

export function overlapsDay(e: Timed, key: string, tz: string): boolean {
  const start = zonedTime(key, tz).getTime();
  const end = zonedTime(addDays(key, 1), tz).getTime();
  const s = new Date(e.starts_at).getTime();
  const en = new Date(e.ends_at).getTime();
  if (e.all_day) return s < end && Math.max(en, s + 1) > start;
  return s < end && en > start;
}

export type Placed<T> = { event: T; top: number; height: number; col: number; cols: number };

/** Position timed events in a day column as fractions of the day, side by side when
 *  they overlap. */
export function layoutDay<T extends Timed>(events: T[], key: string, tz: string): Placed<T>[] {
  const dayStart = zonedTime(key, tz).getTime();
  const dayEnd = zonedTime(addDays(key, 1), tz).getTime();
  const span = dayEnd - dayStart;
  const timed = events
    .filter((e) => !e.all_day && overlapsDay(e, key, tz))
    .map((e) => ({
      e,
      s: Math.max(new Date(e.starts_at).getTime(), dayStart),
      en: Math.min(new Date(e.ends_at).getTime(), dayEnd),
    }))
    .sort((a, b) => a.s - b.s || b.en - a.en);
  const out: Placed<T>[] = [];
  let group: { item: (typeof timed)[number]; col: number }[] = [];
  let groupEnd = -Infinity;
  const flush = () => {
    const cols = Math.max(1, ...group.map((g) => g.col + 1));
    for (const g of group) {
      out.push({
        event: g.item.e,
        top: (g.item.s - dayStart) / span,
        height: Math.max((g.item.en - g.item.s) / span, 15 / 1440),
        col: g.col,
        cols,
      });
    }
    group = [];
  };
  for (const item of timed) {
    if (item.s >= groupEnd && group.length) flush();
    const used = new Set(group.filter((g) => g.item.en > item.s).map((g) => g.col));
    let col = 0;
    while (used.has(col)) col += 1;
    group.push({ item, col });
    groupEnd = Math.max(groupEnd === -Infinity ? item.en : groupEnd, item.en);
  }
  if (group.length) flush();
  return out;
}

export function timeLabel(iso: string, tz: string): string {
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: tz }).format(new Date(iso));
}

export function dayLabel(key: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }): string {
  return new Intl.DateTimeFormat("en-IN", { ...opts, timeZone: "UTC" }).format(new Date(`${key}T00:00:00Z`));
}

/** "2026-11-23T14:30" (local, for <input type="datetime-local">) from an ISO instant. */
export function toLocalInputValue(iso: string, tz: string): string {
  const p = parts(new Date(iso), tz);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${p.y}-${pad(p.m)}-${pad(p.d)}T${pad(p.h)}:${pad(p.min)}`;
}

export function fromLocalInputValue(value: string, tz: string): Date {
  const [d, t = "00:00"] = value.split("T");
  const [hh, mm] = t.split(":").map(Number);
  return zonedTime(d, tz, hh, mm);
}
