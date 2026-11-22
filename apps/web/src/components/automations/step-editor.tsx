"use client";

import { inputCls } from "@/components/life/kit";
import { RISK_LABEL } from "@/lib/format";
import { type AutomationMeta, OP_LABEL, type Step, type ToolInfo, inputKind } from "@/lib/automation";
import { cn } from "@/lib/utils";

type Ref = { label: string; value: string };

/** A text box with a menu that inserts {{values}} from the trigger and earlier steps. */
function RefInput({ label, value, onChange, refs, multiline, placeholder }: { label: string; value: string; onChange: (v: string) => void; refs: Ref[]; multiline?: boolean; placeholder?: string }) {
  const Box = multiline ? "textarea" : "input";
  return (
    <div className="flex gap-1">
      <Box aria-label={label} value={value} onChange={(e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) => onChange(e.target.value)} placeholder={placeholder} rows={multiline ? 3 : undefined} className={cn(inputCls, "min-w-0 flex-1", multiline && "h-auto py-1.5")} />
      {refs.length > 0 && (
        <select aria-label={`Insert a value into ${label}`} value="" onChange={(e) => e.target.value && onChange(`${value}${e.target.value}`)} className={cn(inputCls, "w-9 shrink-0 px-1 text-xs")} title="Insert a value">
          <option value="">{"{}"}</option>
          {refs.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      )}
    </div>
  );
}

function ToolArgs({ tool, args, onChange, refs }: { tool: ToolInfo; args: Record<string, unknown>; onChange: (a: Record<string, unknown>) => void; refs: Ref[] }) {
  const entries = Object.entries(tool.inputs);
  if (!entries.length) return <p className="text-xs text-muted">No inputs needed.</p>;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {entries.map(([key, schema]) => {
        const kind = inputKind(schema);
        const label = `${key.replace(/_/g, " ")}${tool.required.includes(key) ? " *" : ""}`;
        const v = args[key];
        const set = (val: unknown) => {
          const next = { ...args, [key]: val };
          if (val === "" || val === undefined) delete next[key];
          onChange(next);
        };
        return (
          <label key={key} className={cn("text-xs text-muted", (kind === "json" || key === "notes" || key === "body") && "sm:col-span-2")}>
            <span className="capitalize">{label}</span>
            {schema.description && <span className="block text-[11px] text-muted/80">{schema.description}</span>}
            <div className="mt-1">
              {kind === "select" ? (
                <select aria-label={key} value={String(v ?? "")} onChange={(e) => set(e.target.value)} className={cn(inputCls, "w-full")}>
                  <option value="">Default</option>
                  {schema.enum?.map((o) => <option key={o}>{o}</option>)}
                </select>
              ) : kind === "boolean" ? (
                <select aria-label={key} value={v === undefined ? "" : String(v)} onChange={(e) => set(e.target.value === "" ? undefined : e.target.value === "true")} className={cn(inputCls, "w-full")}>
                  <option value="">Default</option><option value="true">Yes</option><option value="false">No</option>
                </select>
              ) : kind === "json" ? (
                <RefInput label={key} value={typeof v === "string" ? v : v === undefined ? "" : JSON.stringify(v)} onChange={(s) => { try { set(s ? JSON.parse(s) : undefined); } catch { set(s); } }} refs={refs} placeholder='e.g. ["a", "b"]' />
              ) : (
                <RefInput label={key} value={v === undefined ? "" : String(v)} onChange={(s) => set(kind === "number" && s && !s.includes("{{") && !Number.isNaN(Number(s)) ? Number(s) : s)} refs={refs} />
              )}
            </div>
          </label>
        );
      })}
    </div>
  );
}

export function StepEditor({ step, onChange, meta, refs }: { step: Step; onChange: (s: Step) => void; meta: AutomationMeta; refs: Ref[] }) {
  const c = step.config;
  const set = (patch: Record<string, unknown>) => onChange({ ...step, config: { ...c, ...patch } });
  const tool = step.kind === "tool" ? meta.tools.find((t) => t.name === c.tool) : undefined;
  return (
    <div className="space-y-2">
      {step.kind === "tool" && (
        <>
          <select aria-label="Action" value={String(c.tool ?? "")} onChange={(e) => onChange({ ...step, config: { tool: e.target.value, args: {} } })} className={cn(inputCls, "w-full")}>
            <option value="">Pick an action</option>
            {meta.tools.map((t) => <option key={t.name} value={t.name}>{t.name} ({RISK_LABEL[t.risk as keyof typeof RISK_LABEL] ?? t.risk})</option>)}
          </select>
          {tool && (
            <>
              <p className="text-xs text-muted">{tool.description}{["sensitive", "irreversible"].includes(tool.risk) && " It asks you before it runs, every time."}</p>
              <ToolArgs tool={tool} args={(c.args as Record<string, unknown>) ?? {}} onChange={(args) => set({ args })} refs={refs} />
            </>
          )}
        </>
      )}
      {step.kind === "agent" && (
        <>
          <RefInput label="What to write" multiline value={String(c.prompt ?? "")} onChange={(v) => set({ prompt: v })} refs={refs} placeholder="e.g. Summarise these tasks in three lines" />
          <p className="text-xs text-muted">Runs on your local model. It sees earlier results as data and won&apos;t follow instructions inside them.</p>
        </>
      )}
      {step.kind === "condition" && (
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr]">
          <RefInput label="Value to check" value={String(c.left ?? "")} onChange={(v) => set({ left: v })} refs={refs} placeholder="Pick a value" />
          <select aria-label="Comparison" value={String(c.op ?? "not_empty")} onChange={(e) => set({ op: e.target.value })} className={inputCls}>
            {meta.condition_ops.map((o) => <option key={o} value={o}>{OP_LABEL[o] ?? o}</option>)}
          </select>
          {!["empty", "not_empty"].includes(String(c.op)) && <RefInput label="Compare with" value={String(c.right ?? "")} onChange={(v) => set({ right: v })} refs={refs} />}
        </div>
      )}
      {step.kind === "approval" && <RefInput label="What you're approving" value={String(c.message ?? "")} onChange={(v) => set({ message: v })} refs={refs} placeholder="e.g. Send this summary to the team?" />}
      {step.kind === "notify" && (
        <>
          <RefInput label="Title" value={String(c.title ?? "")} onChange={(v) => set({ title: v })} refs={refs} placeholder="Notification title" />
          <RefInput label="Message" multiline value={String(c.body ?? "")} onChange={(v) => set({ body: v })} refs={refs} placeholder="Optional" />
        </>
      )}
    </div>
  );
}
