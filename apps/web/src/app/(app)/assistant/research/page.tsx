"use client";

import { SectionTabs } from "@/components/assistant/section-tabs";
import { PageHeader } from "@/components/page-header";
import { ResearchView } from "@/components/research/research-view";

export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="AI Assistant" description="Research from the web, with sources and labels you can check." />
      <SectionTabs />
      <ResearchView />
    </div>
  );
}
