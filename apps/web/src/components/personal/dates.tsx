"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Bell, Trash2 } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { DATE_KINDS, type ImportantDate, daysInMonth, occasion, whenLabel } from "@/lib/personal";
import { cn } from "@/lib/utils";
import { useRefreshPersonal } from "./hooks";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function DateRow({ d }: { d: ImportantDate }) {
  const refresh = useRefreshPersonal("dates");
  const remove = useMutation({ mutationFn: () => api(`/important-dates/${d.id}`, { method: "DELETE" }), onSuccess: refresh });
  const soon = d.days_left !== null && d.days_left <= d.remind_days;
  return (
    <li className="flex items-center gap-3 py-2.5">
      <div className={cn("flex w-14 shrink-0 flex-col items-center rounded-lg border py-1", soon ? "border-warn/40 bg-warn/10" : "border-border")}>
        <span className="text-[10px] uppercase text-muted">{MONTHS[d.month - 1].slice(0, 3)}</span>
        <span className="text-lg font-semibold leading-none tabular-nums">{d.day}</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{d.title}</p>
        <p className="text-xs text-muted">{[whenLabel(d.days_left), occasion(d), d.next ? dayLabel(d.next, { weekday: "short", day: "numeric", month: "short", year: "numeric" }) : null, d.notes].filter(Boolean).join(" · ")}</p>
      </div>
      <span className="hidden items-center gap-1 text-xs text-muted sm:flex"><Bell className="size-3" aria-hidden />{d.remind_days ? `${d.remind_days} days before` : "On the day"}</span>
      <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${d.title}`}><Trash2 className="size-3.5" /></button>
    </li>
  );
}

export function Dates() {
  const refresh = useRefreshPersonal("dates");
  const q = useQuery({ queryKey: ["personal", "dates"], queryFn: () => api<ImportantDate[]>("/important-dates") });
  const [f, setF] = useState({ title: "", kind: "birthday" as ImportantDate["kind"], month: "1", day: "1", year: "", yearly: true, remind_days: "3", notes: "" });
  const add = useMutation({
    mutationFn: () => api("/important-dates", { method: "POST", body: { title: f.title.trim(), kind: f.kind, month: Number(f.month), day: Number(f.day), year: f.year ? Number(f.year) : null, yearly: f.yearly, remind_days: Number(f.remind_days), notes: f.notes || null } }),
    onSuccess: () => { setF({ ...f, title: "", year: "", notes: "" }); refresh(); },
  });
  const maxDay = daysInMonth(Number(f.month));
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <Card>
        <CardTitle>Coming up</CardTitle>
        {q.isLoading ? <Skeleton className="mt-3 h-40" /> : q.isError ? <div className="mt-3"><Alert>Couldn&apos;t load dates.</Alert></div> : !q.data?.length ? <div className="mt-3"><Empty>No dates yet. Add birthdays, anniversaries and renewals and NEXUS reminds you ahead of time.</Empty></div> : (
          <ul className="mt-2 divide-y divide-border">{q.data.map((d) => <DateRow key={d.id} d={d} />)}</ul>
        )}
      </Card>
      <Card className="h-fit">
        <CardTitle>Add a date</CardTitle>
        <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="mt-3 grid grid-cols-2 gap-2">
          <input aria-label="What" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Amma's birthday" className={cn(inputCls, "col-span-2")} />
          <select aria-label="Kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as ImportantDate["kind"] })} className={cn(inputCls, "col-span-2 capitalize")}>{DATE_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</select>
          <select aria-label="Month" value={f.month} onChange={(e) => setF({ ...f, month: e.target.value, day: String(Math.min(Number(f.day), daysInMonth(Number(e.target.value)))) })} className={inputCls}>{MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select>
          <select aria-label="Day" value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} className={inputCls}>{Array.from({ length: maxDay }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}</select>
          <input aria-label="Year" type="number" min={1900} max={2200} value={f.year} onChange={(e) => setF({ ...f, year: e.target.value })} placeholder={f.yearly ? "Year (optional)" : "Year"} className={inputCls} />
          <select aria-label="Remind me" value={f.remind_days} onChange={(e) => setF({ ...f, remind_days: e.target.value })} className={inputCls}>{[0, 1, 3, 7, 14, 30].map((n) => <option key={n} value={n}>{n ? `${n} day${n === 1 ? "" : "s"} before` : "On the day"}</option>)}</select>
          <label className="col-span-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={f.yearly} onChange={(e) => setF({ ...f, yearly: e.target.checked })} />Every year</label>
          <input aria-label="Notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="Notes, e.g. gift ideas" className={cn(inputCls, "col-span-2")} />
          {add.isError && <div className="col-span-2"><Alert>{errorText(add.error)}</Alert></div>}
          <div className="col-span-2"><Button type="submit" className="h-9" loading={add.isPending} disabled={!f.title.trim() || (!f.yearly && !f.year)}>Add date</Button></div>
        </form>
      </Card>
    </div>
  );
}
