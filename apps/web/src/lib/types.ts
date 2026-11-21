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
  | { type: "run.started"; run_id: string; conversation_id: string; user_message: ChatMessage; job: string; provider: "local" | "cloud" }
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
