"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Eye, EyeOff, GripVertical, LayoutGrid, Rows3 } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/card";
import { api } from "@/lib/api";
import { DEFAULT_LAYOUT, mergeLayout, moveWidget, SPAN, updateWidget, type WidgetDef } from "@/lib/home-layout";
import type { HomeLayout, HomeWidgetPref, WidgetSize } from "@/lib/types";
import { cn } from "@/lib/utils";

export type Widget = WidgetDef & { render: () => React.ReactNode };

const SIZES: { value: WidgetSize; label: string }[] = [
  { value: "s", label: "Small" },
  { value: "m", label: "Medium" },
  { value: "l", label: "Wide" },
];

/** The Home grid. Customise lets you drag, resize, hide and switch compact or expanded. */
export function Dashboard({ widgets }: { widgets: Widget[] }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["home-layout"], queryFn: () => api<HomeLayout>("/preferences/home") });
  // Edits apply to the latest layout at once and are saved one after another, so quick clicks
  // never overwrite each other.
  const latest = useRef<HomeLayout | null>(null);
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const [saveError, setSaveError] = useState(false);
  latest.current ??= q.data ?? null;
  const save = (layout: HomeLayout) => {
    latest.current = layout;
    void qc.cancelQueries({ queryKey: ["home-layout"] });
    qc.setQueryData<HomeLayout>(["home-layout"], layout);
    chain.current = chain.current
      .then(() => api<HomeLayout>("/preferences/home", { method: "PUT", body: layout }))
      .then(() => setSaveError(false), () => setSaveError(true));
  };
  const [editing, setEditing] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);

  const layout = latest.current ?? q.data ?? DEFAULT_LAYOUT;
  const items = mergeLayout(widgets, layout.widgets);
  const byId = new Map(widgets.map((w) => [w.id, w]));
  const compact = layout.mode === "compact";
  /** Applies a change to the newest layout (not the one this render saw). */
  const change = (fn: (list: HomeWidgetPref[]) => HomeWidgetPref[], mode?: HomeLayout["mode"]) => {
    const base = latest.current ?? layout;
    save({ mode: mode ?? base.mode, widgets: fn(mergeLayout(widgets, base.widgets)) });
  };
  const visible = items.filter((w) => editing || !w.hidden);
  const hiddenCount = items.filter((w) => w.hidden).length;

  return (
    <section aria-label="Dashboard" className="space-y-3">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {editing && (
          <>
            <div role="radiogroup" aria-label="Layout" className="flex rounded-lg border border-border p-0.5 text-xs">
              {(["expanded", "compact"] as const).map((m) => (
                <button
                  key={m}
                  role="radio"
                  aria-checked={layout.mode === m}
                  onClick={() => change((l) => l, m)}
                  className={cn("flex items-center gap-1 rounded-md px-2 py-1", layout.mode === m ? "bg-raised text-text" : "text-muted")}
                >
                  {m === "expanded" ? <LayoutGrid className="size-3.5" aria-hidden /> : <Rows3 className="size-3.5" aria-hidden />}
                  {m === "expanded" ? "Expanded" : "Compact"}
                </button>
              ))}
            </div>
            <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => change(() => [], "expanded")}>Reset</Button>
          </>
        )}
        <Button variant={editing ? "primary" : "secondary"} className="h-8 px-3 text-xs" disabled={!q.data} onClick={() => setEditing((v) => !v)}>
          {editing ? "Done" : "Customise"}
        </Button>
      </div>
      {saveError && <Alert>Couldn&apos;t save the layout. Try again.</Alert>}
      {!editing && hiddenCount > 0 && <p className="text-right text-xs text-muted">{hiddenCount} hidden</p>}
      <div className={cn("grid grid-cols-1 md:grid-cols-6", compact ? "gap-3" : "gap-4")}>
        {visible.map((w) => {
          const def = byId.get(w.id);
          if (!def) return null;
          const index = items.findIndex((i) => i.id === w.id);
          return (
            <div
              key={w.id}
              data-widget={w.id}
              draggable={editing}
              onDragStart={(e) => {
                setDragId(w.id);
                e.dataTransfer.effectAllowed = "move";
              }}
              onDragOver={(e) => editing && dragId && e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!dragId) return;
                const from = dragId;
                change((l) => moveWidget(l, l.findIndex((i) => i.id === from), l.findIndex((i) => i.id === w.id)));
                setDragId(null);
              }}
              onDragEnd={() => setDragId(null)}
              className={cn(
                "min-w-0",
                SPAN[w.size],
                editing && "rounded-xl outline-dashed outline-1 outline-offset-4 outline-border",
                editing && w.hidden && "opacity-40",
                dragId === w.id && "opacity-50",
                compact && !editing && "[&>div>*]:max-h-64 [&>div>*]:overflow-hidden",
              )}
            >
              {editing && (
                <div className="mb-2 flex flex-wrap items-center gap-1 text-xs">
                  <GripVertical className="size-4 cursor-grab text-muted" aria-hidden />
                  <span className="mr-auto font-medium">{def.title}</span>
                  <button className="rounded p-1 text-muted hover:bg-raised disabled:opacity-30" disabled={index === 0} onClick={() => change((l) => moveWidget(l, index, index - 1))} aria-label={`Move ${def.title} up`}>
                    <ArrowUp className="size-3.5" />
                  </button>
                  <button className="rounded p-1 text-muted hover:bg-raised disabled:opacity-30" disabled={index === items.length - 1} onClick={() => change((l) => moveWidget(l, index, index + 1))} aria-label={`Move ${def.title} down`}>
                    <ArrowDown className="size-3.5" />
                  </button>
                  <label className="sr-only" htmlFor={`size-${w.id}`}>Size of {def.title}</label>
                  <select id={`size-${w.id}`} value={w.size} onChange={(e) => {
                    const size = e.target.value as WidgetSize;
                    change((l) => updateWidget(l, w.id, { size }));
                  }} className="h-7 rounded border border-border bg-surface px-1">
                    {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                  <button className="rounded p-1 text-muted hover:bg-raised" onClick={() => change((l) => updateWidget(l, w.id, { hidden: !l.find((x) => x.id === w.id)?.hidden }))} aria-label={w.hidden ? `Show ${def.title}` : `Hide ${def.title}`}>
                    {w.hidden ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                  </button>
                </div>
              )}
              <div className={cn(editing && "pointer-events-none select-none")}>{def.render()}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
