"use client";

import { useQueryClient } from "@tanstack/react-query";

export function useRefreshPersonal(part: string) {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["personal", part] });
}
