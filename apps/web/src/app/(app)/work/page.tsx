"use client";

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/card";
import { WorkTabs } from "@/components/work/work-tabs";

export default function WorkPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Work" description="Your work log and weekly status, security findings with SLA tracking, project boards, and your OSCP study track." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <WorkTabs />
      </Suspense>
    </div>
  );
}
