"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { TaskBoard } from "@/components/tasks/task-board";
import { useProjects } from "@/components/tasks/hooks";
import { Button } from "@/components/ui/button";
import { Alert, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const projects = useProjects();
  const project = projects.data?.find((p) => p.id === id);
  const archive = useMutation({
    mutationFn: () => api(`/projects/${id}`, { method: "PATCH", body: { status: "archived" } }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["projects"] }); router.push("/projects"); },
  });
  if (projects.isLoading) return <Skeleton className="mx-auto h-40 max-w-5xl" />;
  if (!project) return <div className="mx-auto max-w-5xl"><Alert>Project not found. <Link href="/projects" className="underline">Back to projects</Link></Alert></div>;
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title={project.name} description={project.description ?? undefined}>
        <Button variant="secondary" onClick={() => archive.mutate()} loading={archive.isPending}>Archive</Button>
      </PageHeader>
      <TaskBoard projectId={project.id} />
    </div>
  );
}
