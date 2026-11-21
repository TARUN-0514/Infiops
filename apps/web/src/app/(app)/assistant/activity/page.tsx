"use client";

import { ActivityView } from "@/components/operator/activity-view";
import { SectionTabs } from "@/components/assistant/section-tabs";
import { PageHeader } from "@/components/page-header";

export default function ActivityPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="AI Assistant" description="What NEXUS did on your PC, the web and GitHub." />
      <SectionTabs />
      <ActivityView />
    </div>
  );
}
