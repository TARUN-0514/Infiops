"use client";

import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { PersonalView } from "@/components/personal/personal-view";
import { Skeleton } from "@/components/ui/card";

export default function PersonalPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Personal" description="Goals with milestones, daily routines, lists, a private journal, and the dates you don't want to miss." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <PersonalView />
      </Suspense>
    </div>
  );
}
