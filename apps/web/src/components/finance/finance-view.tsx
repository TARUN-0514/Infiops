"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Stepper, Tabs } from "@/components/life/kit";
import { Alert, Skeleton } from "@/components/ui/card";
import { monthLabel, shiftMonth } from "@/lib/finance";
import { Bills } from "./bills";
import { Budgets } from "./budgets";
import { Debts } from "./debts";
import { Goals } from "./goals";
import { useMeta } from "./hooks";
import { Import } from "./import";
import { Overview } from "./overview";
import { Transactions } from "./transactions";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "transactions", label: "Transactions" },
  { id: "import", label: "Import" },
  { id: "budgets", label: "Budgets" },
  { id: "bills", label: "EMIs and bills" },
  { id: "debts", label: "Debts" },
  { id: "goals", label: "Goals" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export function FinanceView() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const meta = useMeta();
  const raw = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === raw) ? (raw as Tab) : "overview";
  const [month, setMonth] = useState<string | null>(null);
  if (meta.isLoading) return <Skeleton className="h-64" />;
  if (meta.isError || !meta.data) return <Alert>Couldn&apos;t load Finance. Check that the API is running.</Alert>;
  const current = meta.data.month;
  const shown = month ?? current;
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Tabs label="Finance sections" tabs={[...TABS]} value={tab} onChange={(t) => router.replace(`${path}?tab=${t}`, { scroll: false })} />
        {(tab === "overview" || tab === "transactions") && (
          <Stepper label={monthLabel(shown)} onPrev={() => setMonth(shiftMonth(shown, -1))} onNext={() => setMonth(shiftMonth(shown, 1))} nextDisabled={shown >= current} />
        )}
      </div>
      {tab === "overview" && <Overview month={shown} />}
      {tab === "transactions" && <Transactions month={shown} today={meta.data.today} />}
      {tab === "import" && <Import />}
      {tab === "budgets" && <Budgets />}
      {tab === "bills" && <Bills today={meta.data.today} />}
      {tab === "debts" && <Debts />}
      {tab === "goals" && <Goals />}
    </div>
  );
}
