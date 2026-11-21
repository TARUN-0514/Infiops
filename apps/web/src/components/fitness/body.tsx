"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Empty, errorText, inputCls, useChartColors } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type Logs, type Metric, type MetricSpec, num } from "@/lib/fitness";
import { cn } from "@/lib/utils";
import { useMetricSpecs, useRefreshFitness } from "./hooks";

const ORDER: Metric[] = ["weight_kg", "body_fat_pct", "waist_cm", "calories", "protein_g", "water_ml", "sleep_hours"];
const QUICK_WATER = [250, 500, 750];

function LogForm({ specs, today }: { specs: Record<Metric, MetricSpec>; today: string }) {
  const refresh = useRefreshFitness();
  const [metric, setMetric] = useState<Metric>("weight_kg");
  const [value, setValue] = useState("");
  const [day, setDay] = useState(today);
  const [note, setNote] = useState("");
  const add = useMutation({
    mutationFn: (v: { metric: Metric; value: string }) => api("/fitness/logs", { method: "POST", body: { day, metric: v.metric, value: v.value, note: note.trim() || null } }),
    onSuccess: () => { setValue(""); setNote(""); refresh(); },
  });
  const spec = specs[metric];
  return (
    <Card>
      <CardTitle>Log</CardTitle>
      <form onSubmit={(e) => { e.preventDefault(); if (value) add.mutate({ metric, value }); }} className="mt-3 space-y-2">
        <div className="grid gap-2 sm:grid-cols-[1fr_8rem_9rem]">
          <label className="text-sm">What
            <select aria-label="What" value={metric} onChange={(e) => setMetric(e.target.value as Metric)} className={cn(inputCls, "mt-1 w-full")}>
              {ORDER.map((m) => <option key={m} value={m}>{specs[m].label} ({specs[m].unit})</option>)}
            </select>
          </label>
          <label className="text-sm">Value<input required type="number" step="any" min={spec.min} max={spec.max} value={value} onChange={(e) => setValue(e.target.value)} className={cn(inputCls, "mt-1 w-full")} /></label>
          <label className="text-sm">Date<input type="date" required max={today} value={day} onChange={(e) => setDay(e.target.value)} className={cn(inputCls, "mt-1 w-full")} /></label>
        </div>
        <label className="block text-sm">Note (optional)<input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder={metric === "calories" ? "Lunch: dal, rice, sabzi" : ""} className={cn(inputCls, "mt-1 w-full")} /></label>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" className="h-9" loading={add.isPending} disabled={!value}>Save</Button>
          <span className="text-xs text-muted">Water:</span>
          {QUICK_WATER.map((ml) => (
            <Button key={ml} type="button" variant="secondary" className="h-8 px-2" onClick={() => add.mutate({ metric: "water_ml", value: String(ml) })}>+{ml} ml</Button>
          ))}
        </div>
        {spec.sum && <p className="text-xs text-muted">{spec.label} adds up over the day, so log each meal or glass separately.</p>}
        {add.isError && <Alert>{errorText(add.error)}</Alert>}
      </form>
    </Card>
  );
}

function Trend({ metric, spec, data }: { metric: Metric; spec: MetricSpec; data: { day: string; value: string }[] }) {
  const c = useChartColors();
  const rows = data.map((d) => ({ day: d.day, label: dayLabel(d.day, { day: "numeric", month: "short" }), value: Number(d.value) }));
  const latest = rows[rows.length - 1];
  const avg = rows.reduce((n, r) => n + r.value, 0) / Math.max(1, rows.length);
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <CardTitle>{spec.label}</CardTitle>
        <span className="text-sm tabular-nums">
          {spec.sum ? `${num(avg, 0)} ${spec.unit} a day` : `${num(latest?.value)} ${spec.unit}`}
          <span className="ml-1 text-xs text-muted">{spec.sum ? `average, ${rows.length} days` : "latest"}</span>
        </span>
      </div>
      {rows.length < 2 ? <p className="mt-3 text-sm text-muted">One entry so far. The trend appears from the second day.</p> : (
        <div className="mt-3 h-36" aria-label={`${spec.label} over the last 30 days`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fill: c.muted, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis domain={["auto", "auto"]} tick={{ fill: c.muted, fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
              <Tooltip contentStyle={{ background: "rgb(var(--surface))", border: `1px solid ${c.border}`, borderRadius: 8, color: c.text }} formatter={(v) => [`${num(Number(v))} ${spec.unit}`, spec.label]} />
              <Line type="monotone" dataKey="value" stroke={metric === "weight_kg" ? c.accent : c.good} strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

function Recent({ logs, specs }: { logs: Logs; specs: Record<Metric, MetricSpec> }) {
  const refresh = useRefreshFitness();
  const remove = useMutation({ mutationFn: (id: string) => api(`/fitness/logs/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <Card>
      <CardTitle>Recent entries</CardTitle>
      <ul className="mt-3 max-h-96 divide-y divide-border overflow-y-auto">
        {logs.entries.slice(0, 50).map((x) => (
          <li key={x.id} className="flex items-center gap-2 py-1.5 text-sm">
            <span className="w-16 shrink-0 text-xs text-muted">{dayLabel(x.day, { day: "numeric", month: "short" })}</span>
            <span className="min-w-0 flex-1 truncate">{specs[x.metric].label}{x.note && <span className="text-muted"> · {x.note}</span>}</span>
            <span className="tabular-nums">{num(x.value)} {specs[x.metric].unit}</span>
            <button onClick={() => remove.mutate(x.id)} className="rounded p-1 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${specs[x.metric].label} entry`}><Trash2 className="size-3.5" /></button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Body() {
  const specs = useMetricSpecs();
  const logs = useQuery({ queryKey: ["fitness", "logs"], queryFn: () => api<Logs>("/fitness/logs") });
  if (specs.isLoading || logs.isLoading) return <Skeleton className="h-64" />;
  if (specs.isError || logs.isError || !specs.data || !logs.data) return <Alert>Couldn&apos;t load your entries.</Alert>;
  const s = specs.data.metrics;
  const with_data = ORDER.filter((m) => (logs.data.daily[m]?.length ?? 0) > 0);
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <LogForm specs={s} today={specs.data.today} />
        {logs.data.entries.length ? <Recent logs={logs.data} specs={s} /> : <Card><CardTitle>Last 30 days</CardTitle><div className="mt-3"><Empty>Nothing logged yet. Weight, food, water and sleep show up here as charts.</Empty></div></Card>}
      </div>
      {with_data.length > 0 && <div className="grid gap-4 md:grid-cols-2">{with_data.map((m) => <Trend key={m} metric={m} spec={s[m]} data={logs.data.daily[m] ?? []} />)}</div>}
      <p className="text-xs text-muted">For tracking only, not medical advice.</p>
    </div>
  );
}
