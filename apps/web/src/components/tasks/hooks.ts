"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Project, Task } from "@/lib/types";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: () => api<Project[]>("/projects") });
}

export function useTaskMutations() {
  const qc = useQueryClient();
  const done = () => {
    void qc.invalidateQueries({ queryKey: ["tasks"] });
    void qc.invalidateQueries({ queryKey: ["projects"] });
  };
  return {
    create: useMutation({ mutationFn: (body: Record<string, unknown>) => api<Task>("/tasks", { method: "POST", body }), onSuccess: done }),
    update: useMutation({ mutationFn: ({ id, ...body }: { id: string } & Record<string, unknown>) => api<Task>(`/tasks/${id}`, { method: "PATCH", body }), onSuccess: done }),
    complete: useMutation({ mutationFn: (id: string) => api(`/tasks/${id}/complete`, { method: "POST" }), onSuccess: done }),
    postpone: useMutation({ mutationFn: (id: string) => api(`/tasks/${id}/postpone`, { method: "POST", body: { days: 1 } }), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: string) => api(`/tasks/${id}`, { method: "DELETE" }), onSuccess: done }),
  };
}
