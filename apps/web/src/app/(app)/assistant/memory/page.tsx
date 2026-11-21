"use client";

import { Suspense } from "react";
import { MemoryBrowser } from "@/components/assistant/memory-browser";
import { SectionTabs } from "@/components/assistant/section-tabs";
import { PageHeader } from "@/components/page-header";

export default function MemoryPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="AI Assistant" description="What NEXUS remembers about you, where it learned it, and full control to fix or forget it." />
      <SectionTabs />
      <Suspense>
        <MemoryBrowser />
      </Suspense>
    </div>
  );
}
