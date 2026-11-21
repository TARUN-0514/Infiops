"use client";

import { PageHeader } from "@/components/page-header";
import { BriefingHistory, BriefingSettingsCard, BriefingToday } from "@/components/briefing/briefing";

export default function BriefingPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Briefing" description="A short read on your day, written on your PC from your calendar, tasks and email." />
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <BriefingToday />
        <div className="space-y-4">
          <BriefingSettingsCard />
          <BriefingHistory />
        </div>
      </div>
    </div>
  );
}
