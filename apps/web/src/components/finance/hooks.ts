"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Account, FinanceMeta } from "@/lib/finance";

export function useMeta() {
  return useQuery({ queryKey: ["finance", "meta"], queryFn: () => api<FinanceMeta>("/finance/meta"), staleTime: 60_000 });
}

export function useAccounts() {
  return useQuery({ queryKey: ["finance", "accounts"], queryFn: () => api<Account[]>("/finance/accounts") });
}

/** Everything in finance depends on transactions, so refresh it all together. */
export function useRefreshFinance() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["finance"] });
}
