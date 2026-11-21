"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { addDays, dayKey, fromLocalInputValue, toLocalInputValue, zonedTime } from "@/lib/calendar";
import type { CalendarEvent } from "@/lib/types";

export type Draft = Partial<CalendarEvent> & { starts_at: string; ends_at: string };

export function EventDialog({ event, tz, googleConnected, onClose }: { event: Draft; tz: string; googleConnected: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const isNew = !event.id;
  const [title, setTitle] = useState(event.title ?? "");
  const [allDay, setAllDay] = useState(Boolean(event.all_day));
  const [start, setStart] = useState(toLocalInputValue(event.starts_at, tz));
  const [end, setEnd] = useState(toLocalInputValue(event.ends_at, tz));
  const [location, setLocation] = useState(event.location ?? "");
  const [description, setDescription] = useState(event.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);

  const done = () => {
    void qc.invalidateQueries({ queryKey: ["calendar"] });
    onClose();
  };
  const onError = (e: unknown) => setError(e instanceof ApiError ? e.message : "Couldn't save the event.");
  const body = () => {
    if (allDay) {
      const s = start.slice(0, 10);
      const e = end.slice(0, 10) > s ? end.slice(0, 10) : addDays(s, 1);
      return { title, location: location || null, description: description || null, all_day: true, starts_at: zonedTime(s, tz).toISOString(), ends_at: zonedTime(e, tz).toISOString() };
    }
    return { title, location: location || null, description: description || null, all_day: false, starts_at: fromLocalInputValue(start, tz).toISOString(), ends_at: fromLocalInputValue(end, tz).toISOString() };
  };
  const save = useMutation({
    mutationFn: () => (isNew ? api("/calendar/events", { method: "POST", body: body() }) : api(`/calendar/events/${event.id}`, { method: "PATCH", body: body() })),
    onSuccess: done,
    onError,
  });
  const remove = useMutation({ mutationFn: () => api(`/calendar/events/${event.id}`, { method: "DELETE" }), onSuccess: done, onError });
  const invalid = !title.trim() || (!allDay && fromLocalInputValue(end, tz) <= fromLocalInputValue(start, tz));

  return (
    <dialog ref={ref} onClose={onClose} className="w-[min(480px,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-0 text-text backdrop:bg-black/50">
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
        className="space-y-3 p-5"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">{isNew ? "New event" : "Event"}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-raised" aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        <label className="block text-sm">
          <span className="text-muted">Title</span>
          <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-border bg-bg px-3" />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} className="size-4 accent-accent" />
          All day
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-muted">Starts</span>
            <input type={allDay ? "date" : "datetime-local"} value={allDay ? start.slice(0, 10) : start} onChange={(e) => setStart(allDay ? `${e.target.value}T00:00` : e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-border bg-bg px-2" />
          </label>
          <label className="block text-sm">
            <span className="text-muted">Ends</span>
            <input type={allDay ? "date" : "datetime-local"} value={allDay ? end.slice(0, 10) : end} onChange={(e) => setEnd(allDay ? `${e.target.value}T00:00` : e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-border bg-bg px-2" />
          </label>
        </div>
        <label className="block text-sm">
          <span className="text-muted">Location</span>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-border bg-bg px-3" />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Notes</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-border bg-bg p-2" />
        </label>
        {!!event.attendees?.length && (
          <p className="text-xs text-muted">With {event.attendees.filter((a) => !a.self).map((a) => a.name || a.email).join(", ")}</p>
        )}
        {error && <Alert>{error}</Alert>}
        <p className="text-xs text-muted">
          {isNew ? (googleConnected ? "Saved to your Google Calendar." : "Saved in NEXUS only. Connect Google to sync it.") : event.google ? "Changes are saved to Google Calendar." : "This event lives in NEXUS only."}
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <div className="flex gap-2">
            <Button type="submit" loading={save.isPending} disabled={invalid}>{isNew ? "Add" : "Save"}</Button>
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          </div>
          <div className="flex items-center gap-2">
            {event.html_link && (
              <a href={event.html_link} target="_blank" rel="noreferrer noopener" className="flex items-center gap-1 text-xs text-accent hover:underline">
                Google <ExternalLink className="size-3" aria-hidden />
              </a>
            )}
            {!isNew &&
              (confirmDelete ? (
                <Button type="button" variant="danger" onClick={() => remove.mutate()} loading={remove.isPending}>Delete</Button>
              ) : (
                <Button type="button" variant="ghost" onClick={() => setConfirmDelete(true)}>Delete…</Button>
              ))}
          </div>
        </div>
      </form>
    </dialog>
  );
}

export function newDraft(key: string, tz: string, hour = 9): Draft {
  const now = new Date();
  const base = key === dayKey(now, tz) && now.getTime() > zonedTime(key, tz, hour).getTime() ? new Date(Math.ceil(now.getTime() / 1_800_000) * 1_800_000) : zonedTime(key, tz, hour);
  return { starts_at: base.toISOString(), ends_at: new Date(base.getTime() + 3_600_000).toISOString() };
}
