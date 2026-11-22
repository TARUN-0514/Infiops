"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/workspace";

export function useWorkspaces() {
  return useQuery({ queryKey: ["ws", "list"], queryFn: () => api<Workspace[]>("/workspaces") });
}

/** Items, summaries and counts all move together, so refresh them as one. */
export function useRefreshWs() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["ws"] });
}
