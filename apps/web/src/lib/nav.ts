import {
  BarChart3,
  BookOpen,
  Bot,
  Briefcase,
  CalendarDays,
  CheckSquare,
  Dumbbell,
  FolderKanban,
  Heart,
  Home,
  Mail,
  Settings,
  Wallet,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  slug: string;
  href: string;
  label: string;
  icon: LucideIcon;
  /** Roadmap phase in which this module's first version ships. */
  phase: number;
  summary: string;
  coming: string[];
  /** Shipped ahead of the rest of its phase. */
  ready?: boolean;
};

// Order and names follow the blueprint's main navigation, plus Personal (phase 5), which
// the blueprint lists as a module but not as a menu item.
export const NAV: NavItem[] = [
  { slug: "home", href: "/", label: "Home", icon: Home, phase: 0, summary: "Your command centre.", coming: [] },
  {
    slug: "assistant", href: "/assistant", label: "AI Assistant", icon: Bot, phase: 1,
    summary: "Chat with NEXUS, which uses your memory and tools to get things done.",
    coming: ["Streaming chat with history and search", "File uploads and summaries", "Memory with sources you can inspect and correct"],
  },
  {
    slug: "calendar", href: "/calendar", label: "Calendar", icon: CalendarDays, phase: 2,
    summary: "Your schedule, free slots and meeting prep.",
    coming: ["Google Calendar sync", "Day, week and month views", "Conflict detection and free-slot finder"],
  },
  {
    slug: "tasks", href: "/tasks", label: "Tasks", icon: CheckSquare, phase: 1,
    summary: "Everything you need to do, created by typing or speaking naturally.",
    coming: ["Tasks from plain sentences", "Subtasks, priorities and recurring tasks", "List and kanban views"],
  },
  {
    slug: "projects", href: "/projects", label: "Projects", icon: FolderKanban, phase: 1,
    summary: "Group tasks, notes and documents by project.",
    coming: ["Projects with tasks and progress", "Work, personal and learning areas"],
  },
  {
    slug: "emails", href: "/emails", label: "Emails", icon: Mail, phase: 2,
    summary: "Important mail, pending replies and drafts.",
    coming: ["Gmail triage and summaries", "Drafts that wait for your approval", "Follow-up reminders"],
  },
  {
    slug: "knowledge", href: "/knowledge", label: "Knowledge Base", icon: BookOpen, phase: 2,
    summary: "Search and ask questions across your documents.",
    coming: ["Upload PDF, Word, Excel, PowerPoint and images", "Search with cited answers"],
  },
  {
    slug: "finance", href: "/finance", label: "Finance", icon: Wallet, phase: 5,
    summary: "Spending, budgets, EMIs and savings goals.",
    coming: ["Expenses by hand, voice or CSV", "Budgets and payment reminders", "Processed only by the local model"],
  },
  {
    slug: "fitness", href: "/fitness", label: "Fitness", icon: Dumbbell, phase: 5,
    summary: "Workouts, body metrics, sleep and habits.",
    coming: ["Workout logging with sets, reps and weight", "Nutrition, water and sleep", "Weekly progress reports"],
  },
  {
    slug: "personal", href: "/personal", label: "Personal", icon: Heart, phase: 5,
    summary: "Goals, routines, lists, journal and important dates.",
    coming: ["Goals with milestones", "Routines you tick off each day", "Private journal and date reminders"],
  },
  {
    slug: "work", href: "/work", label: "Work", icon: Briefcase, phase: 2,
    summary: "Work log, security workspaces and the OSCP track.",
    coming: ["Work log and weekly status report", "Vulnerability findings with SLA and aging", "AppSec, cloud and pentest boards; OSCP study track"],
  },
  {
    slug: "automations", href: "/automations", label: "Automations", icon: Workflow, phase: 6,
    summary: "Routines that run on a schedule or when something happens.",
    coming: ["Workflows written in plain language", "Approval checkpoints and run history", "Visual workflow builder"],
  },
  {
    slug: "analytics", href: "/analytics", label: "Analytics", icon: BarChart3, phase: 6,
    summary: "Trends in your work, habits, money and fitness.",
    coming: ["Weekly and monthly reports from your real data", "Patterns such as overloaded days and postponed tasks"],
  },
  { slug: "settings", href: "/settings", label: "Settings", icon: Settings, phase: 0, summary: "Profile, appearance and security.", coming: [] },
];

export const CURRENT_PHASE = 6;

/** Not built yet: shows a "coming in phase N" page and a badge in the menu. */
export function isComing(n: NavItem): boolean {
  return n.phase > CURRENT_PHASE && !n.ready;
}

export function findNav(slug: string): NavItem | undefined {
  return NAV.find((n) => n.slug === slug);
}
