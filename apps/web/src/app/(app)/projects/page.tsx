"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { useProjects } from "@/components/tasks/hooks";
import { Button } from "@/components/ui/button";
import { Alert, Card, Skeleton } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const projects = useProjects();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation({
    mutationFn: () => api("/projects", { method: "POST", body: { name: name.trim(), description: description.trim() || null } }),
    onSuccess: () => { setName(""); setDescription(""); void qc.invalidateQueries({ queryKey: ["projects"] }); },
  });
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Projects" description="Group tasks by what they're for: work, home, learning." />
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }} className="mb-6 flex flex-wrap gap-2">
        <label htmlFor="p-name" className="sr-only">Project name</label>
        <input id="p-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="New project name" maxLength={120} className="h-10 min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 text-sm" />
        <label htmlFor="p-desc" className="sr-only">Description</label>
        <input id="p-desc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What it's for (optional)" className="h-10 min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 text-sm" />
        <Button type="submit" loading={create.isPending} disabled={!name.trim()}><Plus className="size-4" />Create</Button>
        {create.isError && <p className="w-full text-sm text-danger" role="alert">{(create.error as ApiError).message}</p>}
      </form>
      {projects.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
      ) : projects.isError ? (
        <Alert>Couldn&apos;t load projects.</Alert>
      ) : !projects.data?.length ? (
        <Card className="py-10 text-center text-sm text-muted">No projects yet. Create one above, or ask NEXUS to add a task to a project.</Card>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.data.map((p) => {
            const total = p.open_tasks + p.done_tasks;
            const pct = total ? Math.round((p.done_tasks / total) * 100) : 0;
            return (
              <li key={p.id}>
                <Link href={`/projects/${p.id}`} className="block h-full rounded-xl border border-border bg-surface/80 p-4 transition-colors hover:border-accent/50">
                  <div className="flex items-center gap-2"><FolderKanban className="size-4 text-accent" aria-hidden /><p className="truncate font-medium">{p.name}</p></div>
                  {p.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{p.description}</p>}
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${p.name} progress`}>
                    <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
                  </div>
                  <p className="mt-1.5 text-xs text-muted">{p.open_tasks} open · {p.done_tasks} done</p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
