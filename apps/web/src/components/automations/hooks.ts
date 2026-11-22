"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AutomationMeta } from "@/lib/automation";

export function useAutomationMeta() {
  return useQuery({ queryKey: ["automations", "meta"], queryFn: () => api<AutomationMeta>("/automations/meta"), staleTime: 300_000 });
}

export function useRefreshAutomations() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["automations"] });
    void qc.invalidateQueries({ queryKey: ["automation-runs"] });
  };
}
