"use client";

import { Suspense } from "react";
import { BriefingView } from "@/components/briefing/briefing-view";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/card";

export default function BriefingPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Briefing" description="Short reads on your day and month, written on your PC from your calendar, tasks, email and logs." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <BriefingView />
      </Suspense>
    </div>
  );
}
