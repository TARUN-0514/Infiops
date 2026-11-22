"use client";

import { Suspense } from "react";
import { AutomationsView } from "@/components/automations/automations-view";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/card";

export default function AutomationsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Automations" description="Routines that run on a schedule or when something happens. Anything sensitive waits for your OK, and payments never run." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <AutomationsView />
      </Suspense>
    </div>
  );
}
