"use client";

import { Suspense } from "react";
import { FinanceView } from "@/components/finance/finance-view";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/card";

export default function FinancePage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Finance" description="Spending, budgets, EMIs, debts and savings. Amounts are encrypted and only the local model ever sees them. NEXUS never makes payments." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <FinanceView />
      </Suspense>
    </div>
  );
}
