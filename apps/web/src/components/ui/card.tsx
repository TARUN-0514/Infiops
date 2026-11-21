import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-border bg-surface/80 p-5 backdrop-blur-sm", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-base font-semibold text-text", className)} {...props} />;
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "good" | "warn"; children: React.ReactNode }) {
  const toneClass = { danger: "border-danger/30 bg-danger/10 text-danger", good: "border-good/30 bg-good/10 text-good", warn: "border-warn/30 bg-warn/10 text-warn" }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-lg border px-3 py-2 text-sm", toneClass)}>
      {children}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-raised", className)} aria-hidden />;
}
