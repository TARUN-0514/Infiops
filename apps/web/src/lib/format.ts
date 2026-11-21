import type { Priority, Risk, Task } from "./types";

export const RISK_LABEL: Record<Risk, string> = {
  read: "Read only",
  draft: "Draft",
  reversible: "Reversible",
  sensitive: "Sensitive",
  irreversible: "Can't be undone",
  forbidden: "Never allowed",
};

export const PRIORITY_LABEL: Record<Priority, string> = { none: "No priority", low: "Low", medium: "Medium", high: "High", urgent: "Urgent" };

export const TOOL_LABEL: Record<string, string> = {
  time_now: "Check the time",
  tasks_create: "Create a task",
  tasks_list: "Look at tasks",
  tasks_update: "Update a task",
  tasks_complete: "Complete a task",
  tasks_delete: "Delete a task",
  projects_list: "Look at projects",
  projects_create: "Create a project",
  memory_search: "Search memory",
  memory_remember: "Save to memory",
  memory_forget: "Forget a memory",
  email_search: "Search email",
  email_read: "Read an email",
  email_draft_reply: "Draft a reply",
  email_send: "Send an email",
  email_follow_up: "Set a follow-up reminder",
  calendar_list: "Check the calendar",
  calendar_free_slots: "Find free time",
  calendar_create_event: "Add a calendar event",
  calendar_update_event: "Change a calendar event",
  calendar_delete_event: "Delete a calendar event",
  calendar_time_block: "Block time for a task",
  kb_search: "Search documents",
  worklog_add: "Add to the work log",
  desktop_open_app: "Open an app on your PC",
  desktop_open_url: "Open a link on your PC",
  files_list: "List a folder on your PC",
  files_read: "Read a file on your PC",
  files_write: "Write a file on your PC",
  files_move: "Move a file on your PC",
  browser_read: "Read a page in NEXUS's browser",
  browser_act: "Use a page in NEXUS's browser",
  computer_use: "Use your screen",
  claude_code_run: "Run Claude Code",
  web_search: "Search the web",
  web_fetch: "Read a web page",
  research_run: "Research a question",
  github_pulls: "List pull requests",
  github_pull: "Read a pull request",
  github_issues: "List issues",
  github_issue: "Read an issue",
};

function dayKey(d: Date, tz: string) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

/** "Today, 18:00", "Tomorrow", "Mon 24 Nov", with overdue detection. */
export function formatDue(task: Pick<Task, "due_at" | "all_day">, tz: string, now = new Date()): { label: string; overdue: boolean } | null {
  if (!task.due_at) return null;
  const due = new Date(task.due_at);
  const today = dayKey(now, tz);
  const tomorrow = dayKey(new Date(now.getTime() + 86_400_000), tz);
  const yesterday = dayKey(new Date(now.getTime() - 86_400_000), tz);
  const key = dayKey(due, tz);
  const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(due);
  let day: string;
  if (key === today) day = "Today";
  else if (key === tomorrow) day = "Tomorrow";
  else if (key === yesterday) day = "Yesterday";
  else
    day = new Intl.DateTimeFormat("en-GB", {
      weekday: "short", day: "numeric", month: "short", timeZone: tz,
      year: key.slice(0, 4) === today.slice(0, 4) ? undefined : "numeric",
    }).format(due);
  const overdue = task.all_day ? key < today : due.getTime() < now.getTime();
  return { label: task.all_day ? day : `${day}, ${time}`, overdue };
}

/** Human text for the RRULE subset NEXUS produces. */
export function describeRecurrence(rule: string | null): string | null {
  if (!rule) return null;
  const parts = Object.fromEntries(rule.split(";").map((p) => p.split("=") as [string, string]));
  const days: Record<string, string> = { MO: "Mon", TU: "Tue", WE: "Wed", TH: "Thu", FR: "Fri", SA: "Sat", SU: "Sun" };
  const every = parts.INTERVAL && parts.INTERVAL !== "1" ? `Every ${parts.INTERVAL} ` : "Every ";
  switch (parts.FREQ) {
    case "DAILY":
      return parts.INTERVAL && parts.INTERVAL !== "1" ? `${every}days` : "Every day";
    case "WEEKLY": {
      const by = parts.BYDAY?.split(",") ?? [];
      if (by.join(",") === "MO,TU,WE,TH,FR") return "Every weekday";
      return by.length ? `${every.trim()} ${by.map((d) => days[d] ?? d).join(", ")}` : parts.INTERVAL && parts.INTERVAL !== "1" ? `${every}weeks` : "Every week";
    }
    case "MONTHLY":
      return parts.BYMONTHDAY ? `Monthly on day ${parts.BYMONTHDAY}` : "Every month";
    case "YEARLY":
      return "Every year";
    default:
      return "Repeats";
  }
}

/** Value for <input type="datetime-local"> in the user's time zone. */
export function toLocalInput(iso: string | null, tz: string): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

/** Inverse of toLocalInput: a local wall time in tz → ISO UTC string. */
export function fromLocalInput(value: string, tz: string): string | null {
  if (!value) return null;
  const asUtc = new Date(`${value}:00Z`);
  // offset of tz at that instant, found by formatting and comparing
  const local = new Date(toLocalInput(asUtc.toISOString(), tz) + ":00Z");
  const offset = local.getTime() - asUtc.getTime();
  return new Date(asUtc.getTime() - offset).toISOString();
}

/** Markdown to plain sentences for text-to-speech. */
export function speakable(md: string): string {
  return md
    .replace(/^#+\s*/gm, "")
    .replace(/\*\*|__|`/g, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\s*\[(\d+)\]/g, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, ". ")
    .replace(/([.!?:])\s*\./g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
