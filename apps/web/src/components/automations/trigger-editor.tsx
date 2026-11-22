"use client";

import { inputCls } from "@/components/life/kit";
import type { AutomationMeta, Trigger } from "@/lib/automation";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function TriggerEditor({ value, onChange, meta }: { value: Trigger; onChange: (t: Trigger) => void; meta: AutomationMeta }) {
  const kind = value.type === "schedule" ? `schedule-${value.every}` : value.type;
  const pick = (k: string) => {
    if (k === "manual") onChange({ type: "manual" });
    else if (k === "event") onChange({ type: "event", event: meta.events[0]?.name ?? "task.created", filter: {} });
    else if (k === "schedule-day") onChange({ type: "schedule", every: "day", at: "08:00", weekdays: [] });
    else if (k === "schedule-month") onChange({ type: "schedule", every: "month", day: 1, at: "09:00" });
    else onChange({ type: "schedule", every: "hours", hours: 4 });
  };
  const ev = value.type === "event" ? meta.events.find((e) => e.name === value.event) : undefined;
  return (
    <div className="space-y-3">
      <select aria-label="When it runs" value={kind} onChange={(e) => pick(e.target.value)} className={cn(inputCls, "w-full sm:w-72")}>
        <option value="schedule-day">On a daily or weekly schedule</option>
        <option value="schedule-month">Once a month</option>
        <option value="schedule-hours">Every few hours</option>
        <option value="event">When something happens</option>
        <option value="manual">Only when I run it</option>
      </select>
      {value.type === "schedule" && value.every === "day" && (
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label="Time" type="time" value={value.at ?? ""} onChange={(e) => onChange({ ...value, at: e.target.value })} className={inputCls} />
          <div className="flex flex-wrap gap-1" role="group" aria-label="Days">
            {WEEKDAYS.map((w, i) => {
              const days = value.weekdays ?? [];
              const on = days.includes(i);
              return <button type="button" key={w} aria-pressed={on} onClick={() => onChange({ ...value, weekdays: on ? days.filter((d) => d !== i) : [...days, i] })} className={cn("rounded-md border px-2 py-1 text-xs", on ? "border-accent/50 bg-accent/15" : "border-border text-muted")}>{w}</button>;
            })}
          </div>
          <span className="text-xs text-muted">{!value.weekdays?.length ? "Every day" : ""} · {meta.timezone}</span>
        </div>
      )}
      {value.type === "schedule" && value.every === "month" && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          Day
          <input aria-label="Day of month" type="number" min={1} max={31} value={value.day ?? 1} onChange={(e) => onChange({ ...value, day: Number(e.target.value) })} className={cn(inputCls, "w-20")} />
          at
          <input aria-label="Time" type="time" value={value.at ?? ""} onChange={(e) => onChange({ ...value, at: e.target.value })} className={inputCls} />
          <span className="text-xs text-muted">Short months use their last day.</span>
        </div>
      )}
      {value.type === "schedule" && value.every === "hours" && (
        <div className="flex items-center gap-2 text-sm">
          Every
          <input aria-label="Hours apart" type="number" min={1} max={168} value={value.hours ?? 1} onChange={(e) => onChange({ ...value, hours: Number(e.target.value) })} className={cn(inputCls, "w-20")} />
          hours
        </div>
      )}
      {value.type === "event" && (
        <div className="space-y-2">
          <select aria-label="Event" value={value.event} onChange={(e) => onChange({ type: "event", event: e.target.value, filter: {} })} className={cn(inputCls, "w-full sm:w-72")}>
            {meta.events.map((e) => <option key={e.name} value={e.name}>{e.label}</option>)}
          </select>
          {ev && (
            <div className="grid gap-2 sm:grid-cols-3">
              {ev.fields.map((f) => (
                <label key={f} className="text-xs text-muted">
                  Only if {f} contains
                  <input aria-label={`Only if ${f} contains`} value={value.filter[f] ?? ""} onChange={(e) => {
                    const filter = { ...value.filter, [f]: e.target.value };
                    if (!e.target.value) delete filter[f];
                    onChange({ ...value, filter });
                  }} placeholder="Anything" className={cn(inputCls, "mt-1 w-full")} />
                </label>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
