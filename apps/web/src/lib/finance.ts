// Finance types and pure helpers. Amounts arrive from the API as decimal strings.

export type TxKind = "expense" | "income" | "transfer";
export type Tx = {
  id: string;
  kind: TxKind;
  amount: string;
  occurred_on: string;
  description: string;
  category: string;
  account_id: string | null;
  to_account_id: string | null;
  notes: string | null;
  source: "manual" | "voice" | "chat" | "csv";
};
export type Account = { id: string; name: string; kind: "bank" | "cash" | "card" | "wallet" | "loan"; opening_balance: string; balance: string; archived: boolean };
export type CategoryLine = { category: string; spent: string; budget: string | null; left: string | null };
export type Upcoming = Recurring;
export type MonthSummary = {
  month: string;
  income: string;
  expense: string;
  net: string;
  count: number;
  categories: CategoryLine[];
  daily: { day: string; spent: string }[];
  days_tracked: number;
  days_elapsed: number;
  over_budget: string[];
  upcoming: Upcoming[];
};
export type CashFlowMonth = { month: string; income: string; expense: string; net: string };
export type FinanceMeta = { expense_categories: string[]; income_categories: string[]; month: string; today: string; currency: string };
export type Recurring = {
  id: string;
  name: string;
  kind: "emi" | "bill" | "subscription" | "rent" | "other";
  amount: string;
  category: string;
  day_of_month: number;
  starts_on: string;
  remaining: number | null;
  account_id: string | null;
  remind_days: number;
  active: boolean;
  last_paid_on: string | null;
  next_due: string | null;
  days_left: number | null;
};
export type Debt = { id: string; name: string; balance: string; annual_rate: string; min_payment: string };
export type PayoffPlan = {
  months: number | null;
  total_interest: string | null;
  feasible: boolean;
  reason?: string;
  order: { id: string; name: string; paid_off_month: number | null; interest: string }[];
};
export type Goal = { id: string; name: string; target: string; saved: string; left: string; target_date: string | null; percent: number; monthly_needed: string | null };
export type ImportRow = { occurred_on: string; kind: "expense" | "income"; amount: string; description: string; category: string; duplicate: boolean };
export type ImportMapping = { date: number; description: number; amount: number | null; debit: number | null; credit: number | null; drcr: number | null; day_first: boolean };
export type ImportPreview = {
  header: string[];
  mapping: ImportMapping | null;
  rows: ImportRow[];
  total: number;
  duplicates: number;
  expense: string;
  income: string;
  errors: string[];
};

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2, minimumFractionDigits: 0 });
const inrShort = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1 });

/** "₹1,25,000" in Indian grouping; whole rupees drop the paise. */
export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "–";
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? inr.format(n) : "–";
}

/** "₹1.2L" for chart axes. */
export function moneyShort(value: number): string {
  return inrShort.format(value);
}

export function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(month: string, style: "long" | "short" = "long"): string {
  const [y, m] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { month: style, year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, 1)));
}

/** Share of a budget used, and how to colour it. */
export function budgetState(spent: string, budget: string | null): { pct: number | null; tone: "good" | "warn" | "danger" } {
  if (!budget || Number(budget) <= 0) return { pct: null, tone: "good" };
  const pct = Math.round((Number(spent) / Number(budget)) * 100);
  return { pct, tone: pct > 100 ? "danger" : pct >= 80 ? "warn" : "good" };
}

export function dueLabel(daysLeft: number | null): string {
  if (daysLeft === null) return "Finished";
  if (daysLeft < 0) return `Overdue by ${-daysLeft} day${daysLeft === -1 ? "" : "s"}`;
  if (daysLeft === 0) return "Due today";
  if (daysLeft === 1) return "Due tomorrow";
  return `Due in ${daysLeft} days`;
}

export function payoffLabel(months: number | null): string {
  if (months === null) return "Never at these payments";
  if (months === 0) return "Nothing owed";
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y ? `${y} yr${y > 1 ? "s" : ""}` : "", m ? `${m} mo` : ""].filter(Boolean).join(" ");
}

/** Signed amount for a list row: spending negative, income positive, transfers neutral. */
export function signed(tx: Pick<Tx, "kind" | "amount">): { text: string; tone: "good" | "text" | "muted" } {
  if (tx.kind === "income") return { text: `+${money(tx.amount)}`, tone: "good" };
  if (tx.kind === "transfer") return { text: money(tx.amount), tone: "muted" };
  return { text: `−${money(tx.amount)}`, tone: "text" };
}

export const ROLE_LABEL: Record<keyof Omit<ImportMapping, "day_first">, string> = {
  date: "Date",
  description: "Description",
  amount: "Amount (one column)",
  debit: "Money out",
  credit: "Money in",
  drcr: "Dr/Cr marker",
};
