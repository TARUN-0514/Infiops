export type CheckState = "ok" | "warn" | "error" | "off";

export interface StatusCheck {
  key: string;
  label: string;
  state: CheckState;
  detail: string;
  [extra: string]: unknown;
}

export interface SystemStatus {
  overall: "ok" | "warn" | "error";
  checked_at: string;
  checks: StatusCheck[];
}

export interface JobRecord {
  last_run: string;
  last_ok: string | null;
  error: string | null;
  failures: number;
  ms: number;
}

const ORDER: Record<CheckState, number> = { error: 0, warn: 1, ok: 2, off: 3 };

/** Problems first, then what's working, then what isn't set up. */
export function sortChecks(checks: StatusCheck[]): StatusCheck[] {
  return [...checks].sort((a, b) => ORDER[a.state] - ORDER[b.state]);
}

export function stateLabel(state: CheckState): string {
  return { ok: "Working", warn: "Needs a look", error: "Not working", off: "Not set up" }[state];
}

export function overallLabel(s: SystemStatus): string {
  const errors = s.checks.filter((c) => c.state === "error").length;
  const warns = s.checks.filter((c) => c.state === "warn").length;
  if (errors) return errors === 1 ? "1 thing isn't working" : `${errors} things aren't working`;
  if (warns) return warns === 1 ? "1 thing needs a look" : `${warns} things need a look`;
  return "Everything is working";
}

/** The failing checks the banner shows, and a signature so dismissing it lasts only until
 * something else breaks. */
export function bannerProblems(s: SystemStatus | undefined): { problems: StatusCheck[]; signature: string } {
  const problems = (s?.checks ?? []).filter((c) => c.state === "error");
  return { problems, signature: problems.map((c) => c.key).sort().join(",") };
}

export function bannerText(problems: StatusCheck[]): string {
  if (!problems.length) return "";
  const [first, ...rest] = problems;
  return rest.length ? `${first.label} and ${rest.length} more aren't working.` : `${first.label} isn't working. ${first.detail}`;
}

export function jobsOf(check: StatusCheck): [string, JobRecord][] {
  const jobs = (check.jobs ?? {}) as Record<string, JobRecord>;
  return Object.entries(jobs).sort(([a], [b]) => a.localeCompare(b));
}

const JOB_NAMES: Record<string, string> = {
  automation_tick: "Automations",
  briefing_tick: "Briefings and check-ins",
  monitor_tick: "Health checks and alerts",
  purge_expired_sessions: "Session clean-up",
  reminders_tick: "Reminders",
  sync_all: "Email and calendar sync",
};

export function jobName(key: string): string {
  return JOB_NAMES[key] ?? key.replace(/_/g, " ");
}
