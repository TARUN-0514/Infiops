"use client";

import { Bar as RBar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors } from "@/components/life/kit";
import { type Analytics, bucketLabel, hours } from "@/lib/analytics";
import { money, moneyShort, monthLabel } from "@/lib/finance";

function useTip() {
  const c = useChartColors();
  return { c, tip: { background: "rgb(var(--surface))", border: `1px solid ${c.border}`, borderRadius: 8, color: c.text } };
}

const axis = (fill: string) => ({ tick: { fill, fontSize: 11 }, tickLine: false, axisLine: false });

export function TasksChart({ a }: { a: Analytics }) {
  const { c, tip } = useTip();
  const data = a.tasks.series.map((s) => ({ label: bucketLabel(s.bucket), Created: s.created, Completed: s.completed }));
  return (
    <div className="h-56" role="img" aria-label="Tasks created and completed">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
          <XAxis dataKey="label" {...axis(c.muted)} minTickGap={16} />
          <YAxis allowDecimals={false} {...axis(c.muted)} width={28} />
          <Tooltip cursor={{ fill: c.border, opacity: 0.4 }} contentStyle={tip} />
          <Legend wrapperStyle={{ fontSize: 12, color: c.muted }} />
          <RBar dataKey="Created" fill={c.muted} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          <RBar dataKey="Completed" fill={c.good} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MeetingsChart({ a }: { a: Analytics }) {
  const { c, tip } = useTip();
  const data = a.time.meetings.series.map((s) => ({ label: bucketLabel(s.bucket), minutes: s.minutes }));
  return (
    <div className="h-40" role="img" aria-label="Meeting time">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
          <XAxis dataKey="label" {...axis(c.muted)} minTickGap={16} />
          <YAxis tickFormatter={(v: number) => `${Math.round(v / 60)}h`} {...axis(c.muted)} width={32} />
          <Tooltip cursor={{ fill: c.border, opacity: 0.4 }} contentStyle={tip} formatter={(v) => [hours(Number(v)), "Meetings"]} />
          <RBar dataKey="minutes" fill={c.accent} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CashFlowChart({ a }: { a: Analytics }) {
  const { c, tip } = useTip();
  const data = a.finance.months.map((m) => ({ month: monthLabel(m.month, "short"), Income: m.income, Spent: m.expense }));
  return (
    <div className="h-48" role="img" aria-label="Income and spending by month">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
          <XAxis dataKey="month" {...axis(c.muted)} />
          <YAxis tickFormatter={moneyShort} {...axis(c.muted)} width={52} />
          <Tooltip cursor={{ fill: c.border, opacity: 0.4 }} contentStyle={tip} formatter={(v, n) => [money(Number(v)), String(n)]} />
          <Legend wrapperStyle={{ fontSize: 12, color: c.muted }} />
          <RBar dataKey="Income" fill={c.good} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          <RBar dataKey="Spent" fill={c.danger} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function WeightChart({ a }: { a: Analytics }) {
  const { c, tip } = useTip();
  const data = a.fitness.weight.map((w) => ({ label: bucketLabel(w.day), kg: w.kg }));
  return (
    <div className="h-40" role="img" aria-label="Body weight">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.border} strokeDasharray="3 3" />
          <XAxis dataKey="label" {...axis(c.muted)} minTickGap={16} />
          <YAxis domain={["dataMin - 1", "dataMax + 1"]} {...axis(c.muted)} width={36} />
          <Tooltip contentStyle={tip} formatter={(v) => [`${Number(v)} kg`, "Weight"]} />
          <Line dataKey="kg" stroke={c.accent} strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
