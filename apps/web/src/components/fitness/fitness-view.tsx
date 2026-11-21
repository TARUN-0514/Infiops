"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs } from "@/components/life/kit";
import { Alert, Skeleton } from "@/components/ui/card";
import { Body } from "./body";
import { Habits } from "./habits";
import { useMetricSpecs } from "./hooks";
import { Report } from "./report";
import { Workouts } from "./workouts";

const TABS = [
  { id: "workouts", label: "Workouts" },
  { id: "body", label: "Body and food" },
  { id: "habits", label: "Habits" },
  { id: "report", label: "This week" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export function FitnessView() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const specs = useMetricSpecs();
  const raw = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === raw) ? (raw as Tab) : "workouts";
  if (specs.isLoading) return <Skeleton className="h-64" />;
  if (specs.isError || !specs.data) return <Alert>Couldn&apos;t load Fitness. Check that the API is running.</Alert>;
  const today = specs.data.today;
  return (
    <div>
      <Tabs label="Fitness sections" tabs={[...TABS]} value={tab} onChange={(t) => router.replace(`${path}?tab=${t}`, { scroll: false })} />
      {tab === "workouts" && <Workouts today={today} />}
      {tab === "body" && <Body />}
      {tab === "habits" && <Habits />}
      {tab === "report" && <Report today={today} />}
    </div>
  );
}
