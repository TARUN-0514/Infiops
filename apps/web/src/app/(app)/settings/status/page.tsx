"use client";

import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { SystemStatusView } from "@/components/settings/system-status";

export default function StatusPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="System status" description="Every part NEXUS depends on, checked now, and what to do when something isn't working.">
        <Link href="/settings" className="text-sm text-accent hover:underline">Back to settings</Link>
      </PageHeader>
      <SystemStatusView />
    </div>
  );
}
