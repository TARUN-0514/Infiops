"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { freshNotifications, showLive } from "@/lib/live-notify";
import type { AppNotification } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

export function NotificationBell({ className }: { className?: string }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ items: AppNotification[]; unread: number }>("/notifications"),
    refetchInterval: 30_000,
  });
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const { fresh, seen: next } = freshNotifications(seen.current, q.data.items);
    seen.current = next;
    void showLive(fresh);
  }, [q.data]);
  const readAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readOne = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unread = q.data?.unread ?? 0;
  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-lg p-2 text-muted hover:bg-raised hover:text-text"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
      >
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="absolute right-1 top-1 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-surface p-2 shadow-xl" role="dialog" aria-label="Notifications">
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-sm font-medium">Notifications</p>
            {unread > 0 && (
              <button onClick={() => readAll.mutate()} className="text-xs text-accent hover:underline">
                Mark all read
              </button>
            )}
          </div>
          {q.isLoading ? (
            <p className="px-2 py-3 text-sm text-muted">Loading…</p>
          ) : q.isError ? (
            <p className="px-2 py-3 text-sm text-danger">Couldn&apos;t load notifications.</p>
          ) : !q.data?.items.length ? (
            <p className="px-2 py-3 text-sm text-muted">Nothing yet. Your morning briefing will show up here.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {q.data.items.map((n) => (
                <li key={n.id}>
                  <Link
                    href={n.link ?? "/"}
                    onClick={() => {
                      if (!n.read) readOne.mutate(n.id);
                      setOpen(false);
                    }}
                    className="block rounded-lg px-2 py-2 hover:bg-raised"
                  >
                    <p className={cn("text-sm", !n.read && "font-medium")}>
                      {!n.read && <span className="mr-1.5 inline-block size-1.5 rounded-full bg-accent align-middle" aria-label="Unread" />}
                      {n.title}
                    </p>
                    {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{n.body}</p>}
                    <p className="mt-0.5 text-[11px] text-muted">{formatDateTime(n.created_at, user?.timezone ?? "UTC")}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
