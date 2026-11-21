"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEmailSummary } from "@/components/email/emails-view";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { addDays, dayKey, timeLabel, zonedTime } from "@/lib/calendar";
import type { CalendarRange } from "@/lib/types";

export function ScheduleCard({ tz }: { tz: string }) {
  const today = dayKey(new Date(), tz);
  const start = zonedTime(today, tz).toISOString();
  const end = zonedTime(addDays(today, 1), tz).toISOString();
  const q = useQuery({
    queryKey: ["calendar", "range", start, end],
    queryFn: () => api<CalendarRange>(`/calendar/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  });
  const now = Date.now();
  const events = (q.data?.events ?? []).filter((e) => e.all_day || new Date(e.ends_at).getTime() > now);
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Schedule</CardTitle>
        <Link href="/calendar" className="text-xs text-accent hover:underline">Calendar</Link>
      </div>
      {q.isLoading ? <Skeleton className="mt-3 h-16" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load today&apos;s events.</Alert></div> : !events.length ? (
        <p className="mt-2 text-sm text-muted">
          Nothing else on today.{" "}
          {!q.data?.google_connected && <Link href="/settings/integrations" className="text-accent hover:underline">Connect Google Calendar</Link>}
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5 text-sm">
          {events.slice(0, 6).map((e) => (
            <li key={e.id} className="flex gap-3">
              <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-muted">{e.all_day ? "All day" : timeLabel(e.starts_at, tz)}</span>
              <span className="min-w-0 flex-1 truncate">{e.title}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function InboxCard() {
  const s = useEmailSummary();
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Email</CardTitle>
        <Link href="/emails" className="text-xs text-accent hover:underline">Emails</Link>
      </div>
      {s.isLoading ? <Skeleton className="mt-3 h-12" /> : s.isError || !s.data ? <div className="mt-3"><Alert>Couldn&apos;t load email.</Alert></div> : !s.data.connected ? (
        <p className="mt-2 text-sm text-muted"><Link href="/settings/integrations" className="text-accent hover:underline">Connect Gmail</Link> to see who is waiting on you.</p>
      ) : (
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div><dt className="text-xs text-muted">Need a reply</dt><dd className="text-xl font-semibold tabular-nums">{s.data.needs_reply}</dd></div>
          <div><dt className="text-xs text-muted">Important</dt><dd className="text-xl font-semibold tabular-nums">{s.data.important}</dd></div>
          <div><dt className="text-xs text-muted">Drafts</dt><dd className="text-xl font-semibold tabular-nums">{s.data.drafts}</dd></div>
        </dl>
      )}
    </Card>
  );
}
