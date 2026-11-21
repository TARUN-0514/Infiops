"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { OctagonX, Play } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import type { OperatorState } from "@/lib/types";
import { cn } from "@/lib/utils";

export function useOperator() {
  return useQuery({ queryKey: ["operator"], queryFn: () => api<OperatorState>("/operator/policy"), refetchInterval: 20_000 });
}

/** Stop everything NEXUS is doing on the PC at once, or resume. */
export function KillSwitch({ className }: { className?: string }) {
  const q = useOperator();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const done = (data: OperatorState) => {
    setError(null);
    qc.setQueryData(["operator"], data);
    void qc.invalidateQueries({ queryKey: ["operator", "activity"] });
  };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "That didn't work. Try again.");
  const stop = useMutation({ mutationFn: () => api<OperatorState>("/operator/stop", { method: "POST" }), onSuccess: done, onError: fail });
  const resume = useMutation({ mutationFn: () => api<OperatorState>("/operator/resume", { method: "POST" }), onSuccess: done, onError: fail });
  const policy = q.data?.policy;
  if (!policy?.enabled) return null;
  return (
    <div className={cn("space-y-2", className)}>
      <div className={cn("flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3", policy.paused ? "border-warn/40 bg-warn/10" : "border-border")}>
        <p className="text-sm" role="status">
          {policy.paused ? "Computer control is paused. NEXUS won't act on your PC until you resume." : "Computer control is on. Stop cancels whatever is running on your PC right now."}
        </p>
        {policy.paused ? (
          <Button variant="secondary" className="h-9" onClick={() => resume.mutate()} loading={resume.isPending}>
            <Play className="size-4" aria-hidden /> Resume
          </Button>
        ) : (
          <Button variant="danger" className="h-9" onClick={() => stop.mutate()} loading={stop.isPending}>
            <OctagonX className="size-4" aria-hidden /> Stop everything
          </Button>
        )}
      </div>
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
