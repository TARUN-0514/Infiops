"use client";

import Link from "next/link";
import { Bar, Empty, Stat } from "@/components/life/kit";
import { Card, CardTitle } from "@/components/ui/card";
import { type Analytics, goalStatus, hours, loadScore, rateLabel, rateTone, weekdayShort } from "@/lib/analytics";
import { dayLabel } from "@/lib/calendar";
import { money } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { CashFlowChart, MeetingsChart, TasksChart, WeightChart } from "./charts";

export function TasksSection({ a }: { a: Analytics }) {
  const t = a.tasks;
  const empty = !t.created && !t.completed;
  return (
    <Card>
      <CardTitle>Tasks</CardTitle>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Completed" value={String(t.completed)} hint={`${t.created} created`} />
        <Stat label="Completion" value={rateLabel(t.completion_rate)} hint="of tasks created in this period" tone={rateTone(t.completion_rate)} />
        <Stat label="On time" value={rateLabel(t.on_time_rate)} hint={t.with_due ? `of ${t.with_due} with a due date` : "no due dates to measure"} tone={rateTone(t.on_time_rate)} />
        <Stat label="Overdue now" value={String(t.overdue)} hint={`${t.open} open`} tone={t.overdue ? "danger" : undefined} />
      </div>
      <div className="mt-5">
        {empty ? <Empty>No tasks were created or completed in this period.</Empty> : <TasksChart a={a} />}
      </div>
      {(t.by_project.length > 0 || t.postponed.length > 0) && (
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          {t.by_project.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">Completed by project</h3>
              <ul className="space-y-2">
                {t.by_project.map((p) => (
                  <li key={p.project}>
                    <div className="mb-1 flex justify-between text-sm"><span>{p.project}</span><span className="tabular-nums text-muted">{p.completed}</span></div>
                    <Bar pct={(100 * p.completed) / Math.max(1, t.completed)} tone="accent" />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {t.postponed.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">Most postponed</h3>
              <ul className="space-y-1.5 text-sm">
                {t.postponed.map((p) => (
                  <li key={p.id} className="flex justify-between gap-3">
                    <span className="truncate">{p.title}</span>
                    <span className={cn("shrink-0 tabular-nums", p.times >= 3 ? "text-warn" : "text-muted")}>{p.times}×</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export function TimeSection({ a }: { a: Analytics }) {
  const t = a.time;
  const max = Math.max(1, ...t.categories.map((c) => c.minutes));
  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <CardTitle>Where time went</CardTitle>
        {t.total_minutes > 0 && <span className="text-sm text-muted">{hours(t.total_minutes)} recorded</span>}
      </div>
      {!t.categories.length ? (
        <div className="mt-4">
          <Empty>
            Nothing recorded yet. Time comes from minutes in your <Link href="/work" className="text-accent hover:underline">work log</Link>, calendar meetings, study sessions and workouts.
          </Empty>
        </div>
      ) : (
        <ul className="mt-4 space-y-2.5">
          {t.categories.map((c) => (
            <li key={`${c.group}-${c.label}`}>
              <div className="mb-1 flex justify-between gap-3 text-sm">
                <span>{c.label} <span className="text-xs text-muted">{c.group}</span></span>
                <span className="tabular-nums text-muted">{hours(c.minutes)}</span>
              </div>
              <Bar pct={(100 * c.minutes) / max} tone="accent" />
            </li>
          ))}
        </ul>
      )}
      {t.work_entries_without_minutes > 0 && (
        <p className="mt-3 text-xs text-muted">{t.work_entries_without_minutes} work log entries have no minutes, so they aren&apos;t counted.</p>
      )}
      {t.meetings.count > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 text-sm font-medium">Meetings ({t.meetings.count})</h3>
          <MeetingsChart a={a} />
        </div>
      )}
    </Card>
  );
}

export function WorkloadSection({ a }: { a: Analytics }) {
  const max = Math.max(1, ...a.workload.map(loadScore));
  return (
    <Card>
      <CardTitle>Workload, next 14 days</CardTitle>
      <p className="mt-1 text-xs text-muted">Meeting hours plus tasks due each day. Red days cross an overload rule.</p>
      <ol className="mt-4 flex h-36 items-end gap-1" aria-label="Load per day">
        {a.workload.map((d) => (
          <li key={d.day} className="flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${dayLabel(d.day)}: ${hours(d.meeting_minutes)} meetings, ${d.tasks_due} tasks due${d.reasons.length ? ` (${d.reasons.join(", ")})` : ""}`}>
            <span className="text-[10px] tabular-nums text-muted">{d.tasks_due || ""}</span>
            <div className={cn("w-full rounded-t", d.overloaded ? "bg-danger" : loadScore(d) ? "bg-accent/70" : "bg-raised")} style={{ height: `${Math.max(4, (100 * loadScore(d)) / max)}%` }} />
            <span className="text-[10px] text-muted">{weekdayShort(d.day).slice(0, 2)}</span>
          </li>
        ))}
      </ol>
      {a.workload.some((d) => d.overloaded) && (
        <ul className="mt-3 space-y-1 text-sm">
          {a.workload.filter((d) => d.overloaded).map((d) => (
            <li key={d.day}><span className="font-medium">{dayLabel(d.day)}</span> <span className="text-muted">{d.reasons.join(", ")}</span></li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function HabitsGoalsSection({ a }: { a: Analytics }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardTitle>Habits</CardTitle>
        {!a.habits.length ? (
          <div className="mt-4"><Empty>No habits yet. Add them in <Link href="/fitness?tab=habits" className="text-accent hover:underline">Fitness</Link>.</Empty></div>
        ) : (
          <ul className="mt-4 space-y-3">
            {a.habits.map((h) => (
              <li key={h.id}>
                <div className="mb-1 flex justify-between gap-3 text-sm">
                  <span>{h.name}</span>
                  <span className="tabular-nums text-muted">{h.done} of {h.target}{h.streak > 1 ? `, ${h.streak}-day streak` : ""}</span>
                </div>
                <Bar pct={h.rate ?? 0} tone={rateTone(h.rate) ?? "accent"} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardTitle>Goals</CardTitle>
        {!a.goals.length ? (
          <div className="mt-4"><Empty>No active goals. Set one in <Link href="/personal?tab=goals" className="text-accent hover:underline">Personal</Link>.</Empty></div>
        ) : (
          <ul className="mt-4 space-y-3">
            {a.goals.map((g) => (
              <li key={g.id}>
                <div className="mb-1 flex justify-between gap-3 text-sm">
                  <span className="truncate">{g.title}</span>
                  <span className={cn("shrink-0 text-xs", g.behind ? "text-warn" : "text-muted")}>{g.progress}%, {goalStatus(g)}</span>
                </div>
                <div className="relative">
                  <Bar pct={g.progress} tone={g.behind ? "warn" : "good"} />
                  {g.expected !== null && g.progress < 100 && (
                    <span className="absolute -top-0.5 h-2.5 w-0.5 rounded bg-text/60" style={{ left: `${g.expected}%` }} aria-hidden />
                  )}
                </div>
                {g.days_left !== null && <p className="mt-0.5 text-xs text-muted">{g.days_left >= 0 ? `${g.days_left} days left` : `${-g.days_left} days past target`}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export function MoneyFitnessSection({ a }: { a: Analytics }) {
  const f = a.fitness;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardTitle>Money</CardTitle>
        {!a.finance.has_data ? (
          <div className="mt-4"><Empty>No income or spending recorded. Add some in <Link href="/finance" className="text-accent hover:underline">Finance</Link>.</Empty></div>
        ) : (
          <>
            <div className="mt-4"><CashFlowChart a={a} /></div>
            {a.finance.top_categories.length > 0 && (
              <>
                <h3 className="mb-2 mt-4 text-sm font-medium">Top spending this month</h3>
                <ul className="space-y-1 text-sm">
                  {a.finance.top_categories.map((c) => (
                    <li key={c.category} className="flex justify-between gap-3">
                      <span className={cn(a.finance.over_budget.includes(c.category) && "text-danger")}>{c.category}{a.finance.over_budget.includes(c.category) ? " (over budget)" : ""}</span>
                      <span className="tabular-nums text-muted">{money(c.spent)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </Card>
      <Card>
        <CardTitle>Fitness</CardTitle>
        {!f.workouts && !f.weight.length && f.sleep_avg === null ? (
          <div className="mt-4"><Empty>No workouts, weight or sleep logged in this period. Log them in <Link href="/fitness" className="text-accent hover:underline">Fitness</Link>.</Empty></div>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-3 gap-3">
              <Stat label="Workouts" value={String(f.workouts)} hint={hours(f.series.reduce((s, x) => s + x.minutes, 0))} />
              <Stat label="Weight" value={f.weight_change === null ? "–" : `${f.weight_change > 0 ? "+" : ""}${f.weight_change.toFixed(1)} kg`} hint={f.weight.length ? `${f.weight.length} readings` : "no readings"} />
              <Stat label="Sleep" value={f.sleep_avg === null ? "–" : `${f.sleep_avg} h`} hint={f.sleep_days ? `avg of ${f.sleep_days} nights` : "not logged"} />
            </div>
            {f.weight.length >= 2 && <div className="mt-4"><WeightChart a={a} /></div>}
          </>
        )}
      </Card>
    </div>
  );
}
