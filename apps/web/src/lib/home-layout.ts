import type { HomeLayout, HomeWidgetPref, WidgetSize } from "./types";

export type WidgetDef = { id: string; title: string; size: WidgetSize };

/** Saved layout first (its order, sizes and hidden flags), then any widgets added since. */
export function mergeLayout(defs: WidgetDef[], saved: HomeWidgetPref[]): HomeWidgetPref[] {
  const known = new Map(defs.map((d) => [d.id, d]));
  const out: HomeWidgetPref[] = [];
  for (const w of saved) {
    if (known.has(w.id) && !out.some((o) => o.id === w.id)) out.push({ id: w.id, size: w.size, hidden: w.hidden });
  }
  for (const d of defs) if (!out.some((o) => o.id === d.id)) out.push({ id: d.id, size: d.size, hidden: false });
  return out;
}

export function moveWidget(list: HomeWidgetPref[], from: number, to: number): HomeWidgetPref[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function updateWidget(list: HomeWidgetPref[], id: string, patch: Partial<HomeWidgetPref>): HomeWidgetPref[] {
  return list.map((w) => (w.id === id ? { ...w, ...patch } : w));
}

/** Column span in the 6-column grid. */
export const SPAN: Record<WidgetSize, string> = { s: "md:col-span-2", m: "md:col-span-3", l: "md:col-span-6" };

export const DEFAULT_LAYOUT: HomeLayout = { mode: "expanded", widgets: [] };
