"use client";

import { XCircle, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useSystemStatus } from "@/components/settings/system-status";
import { bannerProblems, bannerText } from "@/lib/status";

const KEY = "nexus.status-banner.dismissed";

function readDismissed(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** A thin warning across the top of every page while something NEXUS needs is broken. */
export function StatusBanner() {
  const pathname = usePathname();
  const q = useSystemStatus(120_000);
  const { problems, signature } = bannerProblems(q.data);
  const [dismissed, setDismissed] = useState<string | null>(null);
  useEffect(() => setDismissed(readDismissed()), []);
  if (!problems.length || dismissed === signature || pathname.startsWith("/settings/status")) return null;
  return (
    <div role="status" className="mx-auto mb-4 flex max-w-5xl items-start gap-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
      <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1 break-words">
        {bannerText(problems)}{" "}
        <Link href="/settings/status" className="font-medium underline">See system status</Link>
      </p>
      <button
        className="rounded p-0.5 hover:bg-danger/10"
        aria-label="Hide until something else breaks"
        onClick={() => {
          setDismissed(signature);
          try {
            sessionStorage.setItem(KEY, signature);
          } catch {
            /* the banner simply comes back next time */
          }
        }}
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}
