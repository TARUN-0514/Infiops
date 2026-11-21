"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Exercise, Metric, MetricSpec } from "@/lib/fitness";

export function useMetricSpecs() {
  return useQuery({ queryKey: ["fitness", "metrics"], queryFn: () => api<{ metrics: Record<Metric, MetricSpec>; today: string }>("/fitness/metrics"), staleTime: 60_000 });
}

export function useLibrary() {
  return useQuery({ queryKey: ["fitness", "exercises"], queryFn: () => api<Exercise[]>("/fitness/exercises") });
}

export function useRefreshFitness() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["fitness"] });
    void qc.invalidateQueries({ queryKey: ["habits"] });
    void qc.invalidateQueries({ queryKey: ["tracking"] });
  };
}
