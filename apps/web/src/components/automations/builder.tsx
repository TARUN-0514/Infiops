"use client";

// The visual workflow builder: a trigger, then steps as a vertical flow you can edit,
// reorder, add between and remove.
import { useMutation } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Bell, Bot, Filter, Hand, Play, Plus, Trash2, Wrench, Zap } from "lucide-react";
import { useState } from "react";
import { errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { type AutomationMeta, KIND_LABEL, type Step, type StepKind, type Workflow, type WorkflowDraft, availableRefs, blankStep, describeTrigger, draftProblem, moveStep, stepSummary } from "@/lib/automation";
import { cn } from "@/lib/utils";
import { useRefreshAutomations } from "./hooks";
import { StepEditor } from "./step-editor";
import { TriggerEditor } from "./trigger-editor";

const ICON: Record<StepKind, typeof Wrench> = { tool: Wrench, agent: Bot, condition: Filter, approval: Hand, notify: Bell };
const KINDS: StepKind[] = ["tool", "agent", "condition", "approval", "notify"];

function AddStep({ onAdd }: { onAdd: (k: StepKind) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col items-center">
      <div className="h-3 w-px bg-border" />
      {open ? (
        <div className="flex flex-wrap justify-center gap-1 rounded-lg border border-border bg-surface p-1" role="group" aria-label="Step type">
          {KINDS.map((k) => {
            const Icon = ICON[k];
            return <button type="button" key={k} onClick={() => { onAdd(k); setOpen(false); }} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs hover:bg-raised"><Icon className="size-3.5" aria-hidden />{KIND_LABEL[k]}</button>;
          })}
          <button type="button" onClick={() => setOpen(false)} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-raised">Cancel</button>
        </div>
      ) : (
        <button type="button" onClick={() => setOpen(true)} className="flex size-7 items-center justify-center rounded-full border border-border bg-surface text-muted hover:border-accent hover:text-text" aria-label="Add a step here"><Plus className="size-4" /></button>
      )}
      <div className="h-3 w-px bg-border" />
    </div>
  );
}

function StepNode({ i, step, count, meta, refs, onChange, onMove, onRemove }: { i: number; step: Step; count: number; meta: AutomationMeta; refs: { label: string; value: string }[]; onChange: (s: Step) => void; onMove: (to: number) => void; onRemove: () => void }) {
  const Icon = ICON[step.kind];
  return (
    <section aria-label={`Step ${i + 1}`} className="rounded-xl border border-border bg-surface/80 p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent"><Icon className="size-4" aria-hidden /></span>
        <span className="text-xs font-medium uppercase tracking-wide text-muted">{i + 1}. {KIND_LABEL[step.kind]}</span>
        <input aria-label={`Step ${i + 1} label`} value={step.name} onChange={(e) => onChange({ ...step, name: e.target.value })} placeholder={stepSummary({ ...step, name: "" })} className={cn(inputCls, "h-7 min-w-0 flex-1 bg-transparent text-xs")} />
        <button type="button" onClick={() => onMove(i - 1)} disabled={i === 0} className="rounded p-1 text-muted hover:bg-raised disabled:opacity-30" aria-label={`Move step ${i + 1} up`}><ArrowUp className="size-3.5" /></button>
        <button type="button" onClick={() => onMove(i + 1)} disabled={i === count - 1} className="rounded p-1 text-muted hover:bg-raised disabled:opacity-30" aria-label={`Move step ${i + 1} down`}><ArrowDown className="size-3.5" /></button>
        <button type="button" onClick={onRemove} className="rounded p-1 text-muted hover:bg-raised hover:text-danger" aria-label={`Remove step ${i + 1}`}><Trash2 className="size-3.5" /></button>
      </div>
      <StepEditor step={step} onChange={onChange} meta={meta} refs={refs} />
      {(step.kind === "tool" || step.kind === "agent") && (
        <label className="mt-2 flex items-center gap-2 text-xs text-muted">
          If it fails, retry
          <select aria-label={`Step ${i + 1} retries`} value={step.retry_max} onChange={(e) => onChange({ ...step, retry_max: Number(e.target.value) })} className={cn(inputCls, "h-7 text-xs")}>
            {[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n === 0 ? "never" : `${n} time${n === 1 ? "" : "s"}`}</option>)}
          </select>
        </label>
      )}
    </section>
  );
}

export function Builder({ start, id, meta, onDone }: { start: WorkflowDraft; id: string | null; meta: AutomationMeta; onDone: (saved?: Workflow) => void }) {
  const refresh = useRefreshAutomations();
  const [d, setD] = useState<WorkflowDraft>(start);
  const [touched, setTouched] = useState(false);
  const problem = draftProblem(d);
  const save = useMutation({
    mutationFn: () => api<Workflow>(id ? `/automations/${id}` : "/automations", { method: id ? "PUT" : "POST", body: { name: d.name.trim(), description: d.description || null, trigger: d.trigger, steps: d.steps.map((s) => ({ kind: s.kind, name: s.name, config: s.config, retry_max: s.retry_max })), enabled: d.enabled, created_from_prompt: d.created_from_prompt || null } }),
    onSuccess: (w) => { refresh(); onDone(w); },
  });
  const setStep = (i: number, s: Step) => setD({ ...d, steps: d.steps.map((x, j) => (j === i ? s : x)) });
  const insert = (at: number, k: StepKind) => setD({ ...d, steps: [...d.steps.slice(0, at), blankStep(k), ...d.steps.slice(at)] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!problem) save.mutate(); }} className="space-y-4">
      <Card className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-muted">Name<input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="e.g. Weekday morning plan" className={cn(inputCls, "mt-1 w-full")} /></label>
          <label className="text-xs text-muted">Description<input value={d.description ?? ""} onChange={(e) => setD({ ...d, description: e.target.value })} placeholder="Optional" className={cn(inputCls, "mt-1 w-full")} /></label>
        </div>
        {d.created_from_prompt && <p className="text-xs text-muted">Drafted from: “{d.created_from_prompt}”. Check each step before saving.</p>}
      </Card>
      <div className="mx-auto max-w-2xl">
        <section aria-label="Trigger" className="rounded-xl border border-accent/40 bg-accent/5 p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-accent/20 text-accent"><Zap className="size-4" aria-hidden /></span>
            <CardTitle className="text-sm">When: {describeTrigger(d.trigger, (n) => meta.events.find((e) => e.name === n)?.label)}</CardTitle>
          </div>
          <TriggerEditor value={d.trigger} onChange={(trigger) => setD({ ...d, trigger })} meta={meta} />
        </section>
        <AddStep onAdd={(k) => insert(0, k)} />
        {d.steps.map((s, i) => (
          <div key={i}>
            <StepNode i={i} step={s} count={d.steps.length} meta={meta} refs={availableRefs(d.steps, i, d.trigger, meta)} onChange={(x) => setStep(i, x)} onMove={(to) => setD({ ...d, steps: moveStep(d.steps, i, to) })} onRemove={() => setD({ ...d, steps: d.steps.filter((_, j) => j !== i) })} />
            <AddStep onAdd={(k) => insert(i + 1, k)} />
          </div>
        ))}
        <div className="flex justify-center"><span className="rounded-full border border-border px-3 py-1 text-xs text-muted">Done</span></div>
      </div>
      {touched && problem && <Alert>{problem}</Alert>}
      {save.isError && <Alert>{errorText(save.error)}</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" loading={save.isPending}><Play className="size-4" aria-hidden />{id ? "Save changes" : "Save automation"}</Button>
        <Button type="button" variant="ghost" onClick={() => onDone()}>Cancel</Button>
        <label className="ml-auto flex items-center gap-2 text-sm"><input type="checkbox" checked={d.enabled} onChange={(e) => setD({ ...d, enabled: e.target.checked })} />Turned on</label>
      </div>
    </form>
  );
}
