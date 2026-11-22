export type User = {
  id: string;
  email: string;
  display_name: string;
  timezone: string;
  role: "owner" | "member";
  mfa_enabled: boolean;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  csrf_token: string;
  user: User;
};

export type SessionInfo = {
  id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  last_used_at: string;
  current: boolean;
};

export type MfaSetup = { secret: string; otpauth_uri: string };

// --- Phase 1: assistant, memory, tasks ---------------------------------------------

export type Risk = "read" | "draft" | "reversible" | "sensitive" | "irreversible" | "forbidden";

export type MemorySourceRef = { type: "memory"; id: string; content: string; category: string };

export type ChatMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  text: string;
  tools: { id: string; name: string; status: string }[];
  sources: MemorySourceRef[];
  attachments: { id: string; filename: string; content_type: string }[];
  model: string | null;
  created_at: string | null;
};

export type Conversation = { id: string; title: string; created_at: string; updated_at: string };

export type Approval = {
  id: string;
  run_id: string | null;
  conversation_id?: string | null;
  tool_name: string;
  risk: Risk;
  summary: string;
  input: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "expired";
  created_at: string | null;
  expires_at: string;
  decided_at: string | null;
};

export type ChatEvent =
  | { type: "run.started"; run_id: string; conversation_id: string; user_message: ChatMessage; job: string; provider: "local" | "cloud"; cloud_blocked?: "local_data" }
  | { type: "memory.used"; sources: MemorySourceRef[] }
  | { type: "text.delta"; text: string }
  | { type: "tool.started"; id: string; name: string; risk: Risk; summary: string; decision: "allow" | "ask" | "deny" }
  | { type: "tool.finished"; id: string; name: string; status: string; output?: unknown; error?: string | null }
  | { type: "approval.required"; approval: Approval }
  | { type: "message.completed"; message: ChatMessage }
  | { type: "run.finished"; run_id: string; status: string }
  | { type: "error"; code: string; message: string };

export type ToolInfo = {
  name: string;
  description: string;
  risk: Risk;
  default: "allow" | "ask" | "deny";
  policy: "allow" | "ask" | "deny" | null;
  effective: "allow" | "ask" | "deny";
};

export type AiStatus = {
  mode: string;
  local: { enabled: boolean; reachable: boolean; base_url: string; models: Record<string, string> };
  cloud: { enabled: boolean; configured: boolean; ready: boolean; daily_token_budget: number; models: Record<string, string> };
};

export type AiUsage = {
  since: string;
  cloud_tokens_today: number;
  cloud_daily_token_budget: number;
  by_model: { provider: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number | null }[];
};

export type MemoryCategory = "profile" | "preference" | "work" | "people" | "health" | "finance" | "goal" | "routine" | "other";

export type MemoryItem = {
  id: string;
  kind: "semantic" | "episodic" | "procedural";
  category: MemoryCategory;
  content: string;
  confidence: number;
  status: "active" | "inferred" | "superseded";
  privacy: "normal" | "sensitive" | "secret";
  version: number;
  supersedes_id: string | null;
  created_at: string;
  last_used_at: string | null;
  sources: { id: string; source_type: string; source_id: string | null; excerpt: string | null; created_at: string }[];
};

export type MemoryConflict = { id: string; memory: MemoryItem; candidate: { content: string; category?: string }; status: string; created_at: string };

export type TaskStatus = "todo" | "in_progress" | "done" | "cancelled";
export type Priority = "none" | "low" | "medium" | "high" | "urgent";

export type Task = {
  id: string;
  title: string;
  notes: string | null;
  status: TaskStatus;
  priority: Priority;
  due_at: string | null;
  all_day: boolean;
  recurrence: string | null;
  project_id: string | null;
  parent_task_id: string | null;
  postponed_count: number;
  position: number;
  source: string;
  completed_at: string | null;
  created_at: string;
  subtasks_total: number;
  subtasks_done: number;
};

export type ParsedTask = {
  title: string;
  notes: string | null;
  due_at: string | null;
  all_day: boolean;
  priority: Priority;
  recurrence: string | null;
  project_name: string | null;
  project_id: string | null;
  subtasks: string[];
};

export type Project = {
  id: string;
  name: string;
  description: string | null;
  color: string;
  status: "active" | "archived";
  created_at: string;
  open_tasks: number;
  done_tasks: number;
};

// --- Phase 2: integrations, email, calendar, knowledge, work log, briefing ---------

export type SyncResult = { status: string; items: number; error: string | null; at: string } | null;

export type ConnectedAccount = {
  id: string;
  provider: "google";
  account_email: string;
  status: "connected" | "error" | "revoked";
  last_error: string | null;
  last_test_at: string | null;
  last_sync_at: string | null;
  permissions: string[];
  last_sync: { gmail: SyncResult; calendar: SyncResult };
  connected_at: string;
};

export type Integrations = {
  google: { configured: boolean; redirect_uri: string; permissions: string[] };
  accounts: ConnectedAccount[];
};

export type EmailCategory = "action" | "reply" | "fyi" | "newsletter" | "promotion" | "other";

export type EmailMessage = {
  id: string;
  thread_id: string;
  from_name: string;
  from_addr: string;
  to: string[];
  cc?: string[];
  subject: string;
  snippet: string;
  body_text?: string;
  received_at: string;
  is_unread: boolean;
  labels: string[];
  category: EmailCategory | null;
  priority: "low" | "normal" | "high";
  needs_reply: boolean;
  summary: string | null;
  triaged: boolean;
  replied_at: string | null;
};

export type EmailDraft = {
  id: string;
  reply_to_id: string | null;
  to: string[];
  cc: string[];
  subject: string;
  body: string;
  status: "draft" | "pending_approval" | "sent" | "failed" | "discarded";
  source: "manual" | "ai";
  approval_id: string | null;
  error: string | null;
  sent_at: string | null;
  updated_at: string;
};

export type EmailDetail = EmailMessage & { drafts: EmailDraft[]; thread: EmailMessage[] };

export type EmailSummary = {
  connected: boolean;
  account_error: string | null;
  account_email: string | null;
  last_sync_at: string | null;
  needs_reply: number;
  unread: number;
  important: number;
  untriaged: number;
  drafts: number;
};

export type CalendarEvent = {
  id: string;
  title: string;
  description: string | null;
  location: string | null;
  starts_at: string;
  ends_at: string;
  all_day: boolean;
  status: string;
  attendees: { email: string; name: string | null; response: string | null; self: boolean }[];
  html_link: string | null;
  source: "google" | "local" | "time_block";
  google: boolean;
  task_id: string | null;
};

export type CalendarRange = {
  events: CalendarEvent[];
  conflicts: [string, string][];
  google_connected: boolean;
  last_sync_at: string | null;
};

export type FreeSlot = { start: string; end: string; minutes: number };

export type KbDocument = {
  id: string;
  title: string;
  filename: string;
  mime_type: string;
  size: number;
  category: string | null;
  status: "processing" | "ready" | "failed";
  error: string | null;
  pages: number | null;
  chars: number;
  chunks: number;
  summary: string | null;
  created_at: string;
  processed_at: string | null;
  preview?: { ordinal: number; page: number | null; label: string | null; content: string }[];
};

export type Citation = {
  n: number;
  document_id: string;
  title: string;
  page: number | null;
  where: string | null;
  excerpt: string;
  score?: number;
};

export type KbAnswer = { answer: string; citations: Citation[] };

export type WorkLogEntry = {
  id: string;
  day: string;
  content: string;
  minutes: number | null;
  project_id: string | null;
  project: string | null;
  task_id: string | null;
  source: "manual" | "task" | "chat";
  created_at: string;
};

export type Briefing = {
  id: string;
  kind: "morning" | "midday" | "evening" | "weekly_status" | "monthly";
  for_date: string;
  content: string;
  data: Record<string, unknown>;
  model: string | null;
  written_by_model: boolean;
  created_at: string;
  read_at: string | null;
};

export type BriefingSettings = {
  enabled: boolean;
  time: string;
  push: boolean;
  midday: boolean;
  midday_time: string;
  evening: boolean;
  evening_time: string;
  monthly: boolean;
};

export type AppNotification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  read: boolean;
  created_at: string;
};

// --- Phase 3: voice, devices, home layout ---------------------------------------------

export type DeviceMic = "off" | "wake" | "listening" | "thinking" | "speaking";

export type DeviceInfo = {
  id: string;
  name: string;
  kind: string;
  platform: string | null;
  settings: { wake_word: boolean; hands_free: boolean };
  capabilities: Record<string, string | boolean>;
  online: boolean;
  mic: DeviceMic;
  last_seen_at: string | null;
  created_at: string;
};

export type VoiceServerStatus = { ready: boolean; url: string; ms: number | null; error: string | null; voice?: string };
export type VoiceStatus = { enabled: boolean; stt: VoiceServerStatus; tts: VoiceServerStatus };

export type WidgetSize = "s" | "m" | "l";
export type HomeWidgetPref = { id: string; size: WidgetSize; hidden: boolean };
export type HomeLayout = { mode: "compact" | "expanded"; widgets: HomeWidgetPref[] };

// --- Phase 4: computer control, research, GitHub -------------------------------------

export type AllowedApp = { name: string; command: string };
export type AllowedFolder = { path: string; write: boolean };
export type OperatorPolicy = {
  enabled: boolean;
  apps: AllowedApp[];
  folders: AllowedFolder[];
  browser: boolean;
  screen: boolean;
  claude_code: boolean;
  paused: boolean;
};
export type OperatorDevice = {
  id: string;
  name: string;
  online: boolean;
  operator: boolean;
  browser: boolean;
  screen: boolean;
  claude_code: boolean;
};
export type OperatorState = { policy: OperatorPolicy; devices: OperatorDevice[] };

export type ActivityItem = {
  id: string;
  tool: string;
  risk: Risk;
  status: "pending_approval" | "running" | "succeeded" | "failed" | "rejected" | "denied";
  summary: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  run_id: string | null;
  created_at: string;
  finished_at: string | null;
};

export type FindingLabel = "verified" | "assumption" | "opinion";
export type ResearchFinding = { claim: string; label: FindingLabel; sources: number[]; note: string };
export type ResearchSource = { n: number; url: string; title: string; read: boolean; error?: string };
export type ResearchReport = {
  id: string;
  question: string;
  status: "running" | "done" | "failed";
  cloud: boolean;
  summary: string | null;
  findings: ResearchFinding[];
  sources: ResearchSource[];
  queries: string[];
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

export type GithubStatus = { configured: boolean; repos: string[] };
export type GithubTest = {
  configured: boolean;
  connected: boolean;
  login?: string;
  repos: { repo: string; ok: boolean; private?: boolean; error?: string }[];
  error: string | null;
};
