"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, Stat, Stepper } from "@/components/life/kit";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { monthLabel, shiftMonth } from "@/lib/finance";
import { type TrackingMonth, type WeekFacts, type WeekReport, delta, monthGrid, num } from "@/lib/fitness";
import { cn } from "@/lib/utils";

function addDays(day: string, n: number): string {
  return new Date(new Date(`${day}T00:00:00Z`).getTime() + n * 86_400_000).toISOString().slice(0, 10);
}

function Compare({ label, now, before, unit = "", digits = 0 }: { label: string; now: string | number | null; before: string | number | null; unit?: string; digits?: number }) {
  const d = delta(now, before);
  return (
    <Stat
      label={label}
      value={now === null ? "–" : `${num(now, digits)}${unit}`}
      hint={d ? (d.dir === "same" ? "Same as last week" : `${d.text}${unit} vs last week`) : before === null ? "Nothing last week" : undefined}
    />
  );
}

function Week({ today }: { today: string }) {
  const monday = addDays(today, -((new Date(`${today}T00:00:00Z`).getUTCDay() + 6) % 7));
  const [start, setStart] = useState(monday);
  const q = useQuery({ queryKey: ["fitness", "report", start], queryFn: () => api<WeekReport>(`/fitness/report?week_of=${start}`) });
  const label = `${dayLabel(start, { day: "numeric", month: "short" })} – ${dayLabel(addDays(start, 6), { day: "numeric", month: "short" })}`;
  const body = (t: WeekFacts, l: WeekFacts) => (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Compare label="Workouts" now={t.workouts} before={l.workouts} />
        <Compare label="Minutes trained" now={t.minutes} before={l.minutes} />
        <Compare label="Sets" now={t.sets} before={l.sets} />
        <Compare label="Weight moved" now={t.volume_kg} before={l.volume_kg} unit=" kg" />
        <Compare label="Avg calories" now={t.avg.calories} before={l.avg.calories} />
        <Compare label="Avg protein" now={t.avg.protein_g} before={l.avg.protein_g} unit=" g" />
        <Compare label="Avg water" now={t.avg.water_ml} before={l.avg.water_ml} unit=" ml" />
        <Compare label="Avg sleep" now={t.avg.sleep_hours} before={l.avg.sleep_hours} unit=" h" digits={1} />
      </div>
      {t.weight_start && t.weight_end && (
        <p className="mt-3 text-sm">Body weight {num(t.weight_start)} kg → {num(t.weight_end)} kg this week.</p>
      )}
    </>
  );
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>Weekly report</CardTitle>
        <Stepper label={label} onPrev={() => setStart(addDays(start, -7))} onNext={() => setStart(addDays(start, 7))} nextDisabled={start >= monday} />
      </div>
      <div className="mt-4">
        {q.isLoading ? <Skeleton className="h-40" /> : q.isError || !q.data ? <Alert>Couldn&apos;t load the report.</Alert> : (
          <>
            {body(q.data.this_week, q.data.last_week)}
            {q.data.habits.length > 0 && (
              <div className="mt-4 space-y-2">
                <h3 className="text-xs font-medium uppercase tracking-wide text-muted">Habits</h3>
                {q.data.habits.map((h) => (
                  <div key={h.name} className="text-sm">
                    <div className="mb-1 flex justify-between"><span>{h.name}</span><span className="tabular-nums text-muted">{h.done}/{h.target}</span></div>
                    <Bar pct={(h.done / h.target) * 100} tone={h.done >= h.target ? "good" : "accent"} />
                  </div>
                ))}
              </div>
            )}
            <p className="mt-4 text-xs text-muted">{q.data.note}</p>
          </>
        )}
      </div>
    </Card>
  );
}

function Month({ current }: { current: string }) {
  const [month, setMonth] = useState(current);
  const q = useQuery({ queryKey: ["tracking", month], queryFn: () => api<TrackingMonth>(`/tracking/month?month=${month}`) });
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle>Month tracked</CardTitle>
          <p className="mt-1 text-sm text-muted">Days with spending or workouts logged.</p>
        </div>
        <Stepper label={monthLabel(month)} onPrev={() => setMonth(shiftMonth(month, -1))} onNext={() => setMonth(shiftMonth(month, 1))} nextDisabled={month >= current} />
      </div>
      {q.isLoading ? <Skeleton className="mt-4 h-48" /> : q.isError || !q.data ? <div className="mt-4"><Alert>Couldn&apos;t load this month.</Alert></div> : (
        <>
          <div className="mt-4 grid grid-cols-3 gap-3">
            <Stat label="Spending" value={`${q.data.spending_days}/${q.data.days_so_far}`} hint="days" />
            <Stat label="Workouts" value={`${q.data.workout_days}/${q.data.days_so_far}`} hint="days" />
            <Stat label="Anything" value={`${q.data.tracked_days}/${q.data.days_so_far}`} hint="days" />
          </div>
          <div className="mt-4 grid grid-cols-7 gap-1 text-center text-[10px] text-muted">
            {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <span key={i}>{d}</span>)}
            {monthGrid(q.data.days).map((d, i) =>
              d === null ? <span key={i} /> : (
                <div
                  key={d.day}
                  title={`${dayLabel(d.day)}: ${d.spending} spending, ${d.workouts} workout${d.workouts === 1 ? "" : "s"}`}
                  className={cn("flex h-10 flex-col items-center justify-center gap-0.5 rounded-md border text-xs", d.future ? "border-transparent text-muted/40" : d.spending || d.workouts || d.logs ? "border-border bg-raised text-text" : "border-dashed border-border")}
                >
                  <span>{Number(d.day.slice(8))}</span>
                  {!d.future && (
                    <span className="flex gap-0.5" aria-hidden>
                      {d.spending > 0 && <span className="size-1.5 rounded-full bg-accent" />}
                      {d.workouts > 0 && <span className="size-1.5 rounded-full bg-good" />}
                    </span>
                  )}
                </div>
              ),
            )}
          </div>
          <p className="mt-2 flex gap-4 text-xs text-muted">
            <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-accent" />Spending</span>
            <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-good" />Workout</span>
          </p>
        </>
      )}
    </Card>
  );
}

export function Report({ today }: { today: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="lg:col-span-3"><Week today={today} /></div>
      <div className="lg:col-span-2"><Month current={today.slice(0, 7)} /></div>
    </div>
  );
}
