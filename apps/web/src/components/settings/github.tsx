"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Github, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import type { GithubStatus, GithubTest } from "@/lib/types";

/** GitHub, read-only. Shown as connected only after a real test call answers. */
export function GithubIntegration() {
  const q = useQuery({ queryKey: ["integrations", "github"], queryFn: () => api<GithubStatus>("/integrations/github") });
  const test = useMutation({ mutationFn: () => api<GithubTest>("/integrations/github/test", { method: "POST" }) });
  const result = test.data;
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2"><Github className="size-4" aria-hidden /> GitHub (read-only)</CardTitle>
        {q.data?.configured && <Button variant="secondary" className="h-8 px-3" onClick={() => test.mutate()} loading={test.isPending}>Test</Button>}
      </div>
      <p className="mt-1 text-sm text-muted">NEXUS can read pull requests, diffs and issues in the repositories you list, to summarise and review them. It can&apos;t comment, push or merge.</p>
      {q.isLoading ? <Skeleton className="mt-3 h-12" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load GitHub status.</Alert></div> : !q.data?.configured ? (
        <p className="mt-3 text-sm">
          Not set up. Make a fine-grained token with <strong>read-only</strong> access to Contents, Pull requests and Issues for the repositories you want, then set <code className="rounded bg-raised px-1">NEXUS_GITHUB_TOKEN</code> and <code className="rounded bg-raised px-1">NEXUS_GITHUB_REPOS</code> (README › GitHub).
        </p>
      ) : (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-muted">Allowed: {q.data.repos.join(", ") || "none (set NEXUS_GITHUB_REPOS)"}</p>
          {!result && !test.isPending && <p className="text-muted">Not tested yet. Press Test to check the token with a real call.</p>}
          {test.isError && <Alert>{test.error instanceof ApiError ? test.error.message : "The test didn't run."}</Alert>}
          {result && (result.connected ? (
            <>
              <p className="flex items-center gap-2 text-good"><CheckCircle2 className="size-4" aria-hidden /> Connected as {result.login}</p>
              <ul className="space-y-1">
                {result.repos.map((r) => (
                  <li key={r.repo} className="flex items-start gap-2 text-xs">
                    {r.ok ? <CheckCircle2 className="size-3.5 shrink-0 text-good" aria-hidden /> : <XCircle className="size-3.5 shrink-0 text-danger" aria-hidden />}
                    <span>{r.repo}{r.ok ? (r.private ? " · private" : " · public") : `: ${r.error}`}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : <Alert>{result.error ?? "Not connected."}</Alert>)}
        </div>
      )}
    </Card>
  );
}
