"use client";

// Small shared pieces for the Finance and Fitness pages.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export const inputCls = "h-9 rounded-lg border border-border bg-surface px-2 text-sm text-text placeholder:text-muted/70 focus:border-accent";

export function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong. Try again.";
}

export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="-mx-1 mb-6 flex gap-1 overflow-x-auto px-1 pb-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cn("shrink-0 rounded-lg px-3 py-1.5 text-sm", value === t.id ? "bg-accent/15 text-text" : "text-muted hover:bg-raised hover:text-text")}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Stepper({ label, onPrev, onNext, nextDisabled }: { label: string; onPrev: () => void; onNext: () => void; nextDisabled?: boolean }) {
  return (
    <div className="flex items-center gap-1">
      <button onClick={onPrev} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-text" aria-label="Previous">
        <ChevronLeft className="size-4" />
      </button>
      <span className="min-w-32 text-center text-sm font-medium">{label}</span>
      <button onClick={onNext} disabled={nextDisabled} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-text disabled:opacity-40" aria-label="Next">
        <ChevronRight className="size-4" />
      </button>
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "good" | "danger" | "warn" }) {
  return (
    <div className="rounded-xl border border-border bg-surface/80 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold tabular-nums", tone === "good" && "text-good", tone === "danger" && "text-danger", tone === "warn" && "text-warn")}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Bar({ pct, tone = "good" }: { pct: number; tone?: "good" | "warn" | "danger" | "accent" }) {
  const color = { good: "bg-good", warn: "bg-warn", danger: "bg-danger", accent: "bg-accent" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-raised" role="presentation">
      <div className={cn("h-full rounded-full", color)} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">{children}</p>;
}

/** Theme colours as rgb() strings for charts, refreshed when the theme changes. */
export function useChartColors() {
  const read = () => {
    if (typeof window === "undefined") return { accent: "#6e8cff", good: "#4ac991", danger: "#f0646e", muted: "#8c97ad", border: "#273044", text: "#e6eaf2" };
    const s = getComputedStyle(document.documentElement);
    const v = (n: string) => `rgb(${s.getPropertyValue(`--${n}`).trim().split(/\s+/).join(", ")})`;
    return { accent: v("accent"), good: v("good"), danger: v("danger"), muted: v("muted"), border: v("border"), text: v("text") };
  };
  const [c, setC] = useState(read);
  useEffect(() => {
    setC(read());
    const obs = new MutationObserver(() => setC(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return c;
}
