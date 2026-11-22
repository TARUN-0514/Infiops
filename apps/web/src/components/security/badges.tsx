import { SEVERITY_TONE, type Item, type Severity, slaLabel, slaTone } from "@/lib/workspace";
import { cn } from "@/lib/utils";

export function SeverityBadge({ s }: { s: Severity }) {
  return <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-medium capitalize", SEVERITY_TONE[s])}>{s}</span>;
}

export function SlaBadge({ it }: { it: Pick<Item, "days_left" | "closed"> }) {
  const label = slaLabel(it);
  if (!label) return null;
  const tone = slaTone(it);
  return <span className={cn("text-xs tabular-nums", tone === "danger" ? "font-medium text-danger" : tone === "warn" ? "text-warn" : "text-muted")}>{label}</span>;
}
