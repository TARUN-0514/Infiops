"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/assistant", label: "Chat" },
  { href: "/assistant/memory", label: "Memory" },
  { href: "/assistant/research", label: "Research" },
  { href: "/assistant/approvals", label: "Approvals" },
  { href: "/assistant/activity", label: "Activity" },
];

export function usePendingApprovals() {
  return useQuery({ queryKey: ["approvals", "pending"], queryFn: () => api<Approval[]>("/approvals?status=pending"), refetchInterval: 30_000 });
}

export function SectionTabs() {
  const pathname = usePathname();
  const pending = usePendingApprovals().data?.length ?? 0;
  return (
    <nav aria-label="Assistant sections" className="mb-6 flex gap-1 overflow-x-auto border-b border-border">
      {TABS.map((t) => {
        const active = t.href === "/assistant" ? pathname === "/assistant" : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? "page" : undefined}
            className={cn("-mb-px flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm", active ? "border-accent text-text" : "border-transparent text-muted hover:text-text")}
          >
            {t.label}
            {t.label === "Approvals" && pending > 0 && (
              <span className="rounded-full bg-warn/20 px-1.5 text-xs text-warn" aria-label={`${pending} waiting`}>{pending}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
