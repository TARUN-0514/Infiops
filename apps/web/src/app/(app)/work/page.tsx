"use client";

import { PageHeader } from "@/components/page-header";
import { WorkView } from "@/components/work/work-view";

export default function WorkPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Work" description="What you did, and a weekly status report written from it. The security workspaces arrive in phase 5." />
      <WorkView />
    </div>
  );
}
