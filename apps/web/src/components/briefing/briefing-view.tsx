"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs } from "@/components/life/kit";
import { BriefingHistory, BriefingSettingsCard, BriefingToday } from "./briefing";
import { CheckinPanel, MonthlyReports } from "./checkins";

const TABS = [
  { id: "morning", label: "Morning" },
  { id: "midday", label: "Midday" },
  { id: "evening", label: "Evening" },
  { id: "monthly", label: "Monthly" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export function BriefingView() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const raw = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === raw) ? (raw as Tab) : "morning";
  return (
    <div>
      <Tabs label="Briefings" tabs={[...TABS]} value={tab} onChange={(t) => router.replace(`${path}?tab=${t}`, { scroll: false })} />
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        {tab === "morning" && <BriefingToday />}
        {(tab === "midday" || tab === "evening") && <CheckinPanel kind={tab} />}
        {tab === "monthly" && <MonthlyReports />}
        <div className="space-y-4">
          <BriefingSettingsCard />
          {tab !== "monthly" && <BriefingHistory kind={tab} />}
        </div>
      </div>
    </div>
  );
}
