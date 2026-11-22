"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs } from "@/components/life/kit";
import { useToday } from "@/lib/today";
import { Dates } from "./dates";
import { Goals } from "./goals";
import { Journal } from "./journal";
import { Lists } from "./lists";
import { Routines } from "./routines";

const TABS = [
  { id: "goals", label: "Goals" },
  { id: "routines", label: "Routines" },
  { id: "lists", label: "Lists" },
  { id: "journal", label: "Journal" },
  { id: "dates", label: "Important dates" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export function PersonalView() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const today = useToday();
  const raw = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === raw) ? (raw as Tab) : "goals";
  return (
    <div>
      <Tabs label="Personal sections" tabs={[...TABS]} value={tab} onChange={(t) => router.replace(`${path}?tab=${t}`, { scroll: false })} />
      {tab === "goals" && <Goals />}
      {tab === "routines" && <Routines today={today} />}
      {tab === "lists" && <Lists />}
      {tab === "journal" && <Journal today={today} />}
      {tab === "dates" && <Dates />}
    </div>
  );
}
