"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useMeta, useRefreshFinance } from "./hooks";

type Budget = { category: string; monthly_limit: string };

export function Budgets() {
  const meta = useMeta();
  const refresh = useRefreshFinance();
  const q = useQuery({ queryKey: ["finance", "budgets"], queryFn: () => api<Budget[]>("/finance/budgets") });
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (q.data) setValues(Object.fromEntries(q.data.map((b) => [b.category, String(Number(b.monthly_limit))])));
  }, [q.data]);
  const save = useMutation({
    mutationFn: () =>
      api("/finance/budgets", {
        method: "PUT",
        body: Object.entries(values).filter(([, v]) => v && Number(v) > 0).map(([category, v]) => ({ category, monthly_limit: v })),
      }),
    onSuccess: () => { setSaved(true); refresh(); },
  });
  if (q.isLoading || meta.isLoading) return <Skeleton className="h-64" />;
  if (q.isError || meta.isError) return <Alert>Couldn&apos;t load budgets.</Alert>;
  const total = Object.values(values).reduce((n, v) => n + (Number(v) || 0), 0);
  return (
    <Card>
      <CardTitle>Monthly budgets</CardTitle>
      <p className="mt-1 text-sm text-muted">Set a limit for the categories you want to watch. Leave the rest empty. The Overview shows how much is left.</p>
      <form onSubmit={(e) => { e.preventDefault(); setSaved(false); save.mutate(); }} className="mt-4 space-y-3">
        <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {meta.data?.expense_categories.map((c) => (
            <label key={c} className="flex items-center justify-between gap-3 text-sm">
              <span>{c}</span>
              <span className="flex items-center gap-1">
                <span className="text-muted">₹</span>
                <input type="number" min="0" step="100" value={values[c] ?? ""} onChange={(e) => { setSaved(false); setValues((v) => ({ ...v, [c]: e.target.value })); }} placeholder="No limit" className={cn(inputCls, "w-32 text-right")} aria-label={`${c} monthly limit`} />
              </span>
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <Button type="submit" className="h-9" loading={save.isPending}>Save budgets</Button>
          <span className="text-sm text-muted">Total ₹{total.toLocaleString("en-IN")} a month</span>
          {saved && <span className="text-sm text-good" role="status">Saved.</span>}
        </div>
        {save.isError && <Alert>{errorText(save.error)}</Alert>}
      </form>
    </Card>
  );
}
