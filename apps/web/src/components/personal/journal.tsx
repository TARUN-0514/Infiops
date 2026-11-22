"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Lock, Pencil, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, Stepper, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { monthLabel, shiftMonth } from "@/lib/finance";
import { type JournalEntry, type JournalMonth, MOODS, parseTags } from "@/lib/personal";
import { cn } from "@/lib/utils";
import { useRefreshPersonal } from "./hooks";

type Draft = { day: string; mood: number | null; content: string; tags: string };

function Composer({ start, onSave, saving, onCancel }: { start: Draft; onSave: (d: Draft) => void; saving: boolean; onCancel?: () => void }) {
  const [d, setD] = useState(start);
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave(d); }} className="space-y-2">
      <textarea aria-label="Journal entry" value={d.content} onChange={(e) => setD({ ...d, content: e.target.value })} rows={5} placeholder="How was today?" className={cn(inputCls, "h-auto w-full py-2 leading-relaxed")} />
      <div className="flex flex-wrap items-center gap-2">
        <input aria-label="Entry day" type="date" max={start.day} value={d.day} onChange={(e) => setD({ ...d, day: e.target.value })} className={inputCls} />
        <div className="flex gap-1" role="group" aria-label="Mood">
          {MOODS.slice(1).map((m, i) => (
            <button type="button" key={m} aria-pressed={d.mood === i + 1} onClick={() => setD({ ...d, mood: d.mood === i + 1 ? null : i + 1 })} className={cn("rounded-md border px-2 py-1 text-xs", d.mood === i + 1 ? "border-accent/50 bg-accent/15" : "border-border text-muted")}>{m}</button>
          ))}
        </div>
        <input aria-label="Tags" value={d.tags} onChange={(e) => setD({ ...d, tags: e.target.value })} placeholder="Tags, e.g. family, oscp" className={cn(inputCls, "min-w-0 flex-1 basis-40")} />
      </div>
      <div className="flex gap-2">
        <Button type="submit" className="h-9" loading={saving} disabled={!d.content.trim()}>Save entry</Button>
        {onCancel && <Button type="button" variant="ghost" className="h-9" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}

function payload(d: Draft) {
  return { day: d.day, mood: d.mood, content: d.content.trim(), tags: parseTags(d.tags) };
}

function Entry({ e }: { e: JournalEntry }) {
  const refresh = useRefreshPersonal("journal");
  const [editing, setEditing] = useState(false);
  const save = useMutation({ mutationFn: (d: Draft) => api(`/journal/${e.id}`, { method: "PUT", body: payload(d) }), onSuccess: () => { setEditing(false); refresh(); } });
  const remove = useMutation({ mutationFn: () => api(`/journal/${e.id}`, { method: "DELETE" }), onSuccess: refresh });
  if (editing) return <li className="py-3"><Composer start={{ day: e.day, mood: e.mood, content: e.content, tags: e.tags.join(", ") }} onSave={(d) => save.mutate(d)} saving={save.isPending} onCancel={() => setEditing(false)} />{save.isError && <Alert>{errorText(save.error)}</Alert>}</li>;
  return (
    <li className="group py-3">
      <div className="flex items-center gap-2">
        <p className="flex-1 text-xs font-medium uppercase tracking-wide text-muted">{dayLabel(e.day, { weekday: "long", day: "numeric", month: "short" })}{e.mood && <span className="ml-2 normal-case tracking-normal">· {MOODS[e.mood]}</span>}</p>
        <button onClick={() => setEditing(true)} className="rounded p-1.5 text-muted opacity-100 hover:bg-raised sm:opacity-0 sm:group-hover:opacity-100" aria-label="Edit entry"><Pencil className="size-3.5" /></button>
        <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted opacity-100 hover:bg-raised hover:text-danger sm:opacity-0 sm:group-hover:opacity-100" aria-label="Delete entry"><Trash2 className="size-3.5" /></button>
      </div>
      <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{e.content}</p>
      {e.tags.length > 0 && <p className="mt-1 text-xs text-accent">{e.tags.map((t) => `#${t}`).join(" ")}</p>}
    </li>
  );
}

export function Journal({ today }: { today: string }) {
  const refresh = useRefreshPersonal("journal");
  const current = today.slice(0, 7);
  const [month, setMonth] = useState(current);
  const [search, setSearch] = useState("");
  const [key, setKey] = useState(0);
  const params = new URLSearchParams({ month, ...(search.trim() ? { q: search.trim() } : {}) });
  const q = useQuery({ queryKey: ["personal", "journal", params.toString()], queryFn: () => api<JournalMonth>(`/journal?${params}`) });
  const add = useMutation({ mutationFn: (d: Draft) => api("/journal", { method: "POST", body: payload(d) }), onSuccess: () => { setKey((k) => k + 1); refresh(); } });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <Card className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Journal</CardTitle>
          <Stepper label={monthLabel(month)} onPrev={() => setMonth(shiftMonth(month, -1))} onNext={() => setMonth(shiftMonth(month, 1))} nextDisabled={month >= current} />
        </div>
        <div className="relative mt-3">
          <Search className="absolute left-2 top-2.5 size-4 text-muted" aria-hidden />
          <input aria-label="Search this month" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search this month" className={cn(inputCls, "w-full pl-8")} />
        </div>
        {q.isLoading ? <Skeleton className="mt-3 h-40" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load the journal.</Alert></div> : !q.data?.entries.length ? (
          <div className="mt-3"><Empty>{search ? "No entries match." : `Nothing written in ${monthLabel(month)}.`}</Empty></div>
        ) : (
          <>
            <p className="mt-3 text-xs text-muted">{q.data.days_written} day{q.data.days_written === 1 ? "" : "s"} written{q.data.average_mood !== null && ` · average mood ${q.data.average_mood} of 5`}</p>
            <ul className="divide-y divide-border">{q.data.entries.map((e) => <Entry key={e.id} e={e} />)}</ul>
          </>
        )}
      </Card>
      <Card className="h-fit">
        <CardTitle>Write</CardTitle>
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted"><Lock className="size-3" aria-hidden />Encrypted at rest. Chat only reads or writes it on the local model.</p>
        <div className="mt-3"><Composer key={key} start={{ day: today, mood: null, content: "", tags: "" }} onSave={(d) => add.mutate(d)} saving={add.isPending} /></div>
        {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      </Card>
    </div>
  );
}
