"use client";

import { Suspense } from "react";
import { AnalyticsView } from "@/components/analytics/analytics-view";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/card";

export default function AnalyticsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Analytics" description="What needs attention, and how your work, time, habits, money and fitness are trending." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <AnalyticsView />
      </Suspense>
    </div>
  );
}
