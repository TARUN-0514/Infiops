"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FolderLock, FolderOpen, Plus, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { KillSwitch, useOperator } from "@/components/operator/kill-switch";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { EMPTY_POLICY, policyProblems } from "@/lib/operator";
import type { OperatorDevice, OperatorPolicy, OperatorState } from "@/lib/types";
import { cn } from "@/lib/utils";

function Toggle({ label, hint, checked, onChange, disabled }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  const id = useId();
  return (
    <div className={cn("flex items-start justify-between gap-4 py-3", disabled && "opacity-60")}>
      <div className="min-w-0">
        <p id={`${id}-l`} className="text-sm font-medium">{label}</p>
        <p id={`${id}-h`} className="text-xs text-muted">{hint}</p>
      </div>
      <button
        type="button" role="switch" aria-checked={checked} aria-labelledby={`${id}-l`} aria-describedby={`${id}-h`} disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn("relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition-colors disabled:cursor-not-allowed", checked ? "border-accent bg-accent" : "border-border bg-raised")}
      >
        <span className={cn("absolute left-0 top-0.5 size-[18px] rounded-full bg-text shadow transition-transform", checked ? "translate-x-[22px] bg-accent-fg" : "translate-x-0.5")} aria-hidden />
      </button>
    </div>
  );
}

function DeviceLine({ d }: { d: OperatorDevice }) {
  const ready = d.online && d.operator;
  const extras = [d.browser && "browser", d.screen && "screen", d.claude_code && "Claude Code"].filter(Boolean).join(", ");
  return (
    <li className="flex items-start gap-2 py-2 text-sm">
      {ready ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> : <XCircle className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />}
      <div className="min-w-0">
        <p>{d.name} · {!d.online ? "offline" : d.operator ? "ready" : "online, control blocked on the PC"}</p>
        <p className="text-xs text-muted">
          {!d.online ? "Start the NEXUS app or nexus-agent run." : d.operator ? `Can also use: ${extras || "files and apps only"}` : "On the PC, run: nexus-agent control on, then restart the agent."}
        </p>
      </div>
    </li>
  );
}

const input = "h-9 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text placeholder:text-muted/70 focus:border-accent";

export function ComputerControl() {
  const q = useOperator();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<OperatorPolicy>(EMPTY_POLICY);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (q.data && !dirty) setDraft(q.data.policy);
  }, [q.data, dirty]);

  const edit = (fn: (p: OperatorPolicy) => OperatorPolicy) => {
    setDraft((p) => fn(p));
    setDirty(true);
    setSaved(false);
  };
  const save = useMutation({
    mutationFn: (p: OperatorPolicy) => api<OperatorState>("/operator/policy", { method: "PUT", body: { ...p, paused: q.data?.policy.paused ?? false } }),
    onSuccess: (data) => {
      qc.setQueryData(["operator"], data);
      setDraft(data.policy);
      setDirty(false);
      setSaved(true);
      setError(null);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't save. Try again."),
  });

  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError) return <Alert>Couldn&apos;t load computer control settings.</Alert>;
  const problems = policyProblems(draft);
  const devices = q.data?.devices ?? [];

  return (
    <div className="space-y-6">
      <KillSwitch />
      <Card>
        <CardTitle>Your PC</CardTitle>
        {devices.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No PC is paired. Pair one in <Link className="text-accent hover:underline" href="/settings/devices">Voice and devices</Link>.</p>
        ) : (
          <ul className="mt-1 divide-y divide-border">{devices.map((d) => <DeviceLine key={d.id} d={d} />)}</ul>
        )}
      </Card>

      <Card>
        <CardTitle>What NEXUS may do</CardTitle>
        <p className="mt-1 text-sm text-muted">Everything is off until you allow it. NEXUS checks these rules on the server and again on your PC. Writing, moving, browser actions, screen control and Claude Code always ask you first.</p>
        <div className="mt-2 divide-y divide-border">
          <Toggle label="Computer control" hint="Let NEXUS open your allowed apps and use your allowed folders." checked={draft.enabled} onChange={(v) => edit((p) => ({ ...p, enabled: v }))} />
          <Toggle label="NEXUS's own browser" hint="A separate Chromium profile on your PC. It never sees your own browser, passwords or sign-ins." checked={draft.browser} disabled={!draft.enabled} onChange={(v) => edit((p) => ({ ...p, browser: v }))} />
          <Toggle label="Claude Code" hint="Run Claude Code in an allowed project folder. Plan-only unless you allow edits for that run." checked={draft.claude_code} disabled={!draft.enabled} onChange={(v) => edit((p) => ({ ...p, claude_code: v }))} />
          <Toggle label="Screen control" hint="Mouse and keyboard, for tasks no other tool can do. Uses Claude in the cloud, so screenshots leave your PC." checked={draft.screen} disabled={!draft.enabled} onChange={(v) => edit((p) => ({ ...p, screen: v }))} />
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Allowed folders</CardTitle>
          <Button variant="secondary" className="h-8 px-3" onClick={() => edit((p) => ({ ...p, folders: [...p.folders, { path: "", write: false }] }))} disabled={draft.folders.length >= 20}>
            <Plus className="size-4" aria-hidden /> Add folder
          </Button>
        </div>
        <p className="mt-1 text-sm text-muted">NEXUS can only see inside these folders. System folders and the agent&apos;s own folder are always off limits.</p>
        {draft.folders.length === 0 ? <p className="mt-3 text-sm text-muted">No folders yet.</p> : (
          <ul className="mt-3 space-y-2">
            {draft.folders.map((f, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
                {f.write ? <FolderOpen className="size-4 shrink-0 text-accent" aria-hidden /> : <FolderLock className="size-4 shrink-0 text-muted" aria-hidden />}
                <input aria-label={`Folder ${i + 1}`} className={cn(input, "min-w-0 flex-1")} placeholder="C:\Users\you\Documents\NEXUS" value={f.path}
                  onChange={(e) => edit((p) => ({ ...p, folders: p.folders.map((x, j) => (j === i ? { ...x, path: e.target.value } : x)) }))} />
                <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted">
                  <input type="checkbox" checked={f.write} onChange={(e) => edit((p) => ({ ...p, folders: p.folders.map((x, j) => (j === i ? { ...x, write: e.target.checked } : x)) }))} />
                  Can write
                </label>
                <Button variant="ghost" className="h-9 w-9 shrink-0 px-0" aria-label={`Remove folder ${i + 1}`} onClick={() => edit((p) => ({ ...p, folders: p.folders.filter((_, j) => j !== i) }))}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Allowed apps</CardTitle>
          <Button variant="secondary" className="h-8 px-3" onClick={() => edit((p) => ({ ...p, apps: [...p.apps, { name: "", command: "" }] }))} disabled={draft.apps.length >= 40}>
            <Plus className="size-4" aria-hidden /> Add app
          </Button>
        </div>
        <p className="mt-1 text-sm text-muted">NEXUS starts only these exact commands, without a shell.</p>
        {draft.apps.length === 0 ? <p className="mt-3 text-sm text-muted">No apps yet. For example: Notepad, notepad.exe.</p> : (
          <ul className="mt-3 space-y-2">
            {draft.apps.map((a, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
                <input aria-label={`App ${i + 1} name`} className={cn(input, "sm:w-40")} placeholder="VS Code" value={a.name}
                  onChange={(e) => edit((p) => ({ ...p, apps: p.apps.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) }))} />
                <input aria-label={`App ${i + 1} command`} className={cn(input, "min-w-0 flex-1 font-mono")} placeholder='"C:\Program Files\App\app.exe"' value={a.command}
                  onChange={(e) => edit((p) => ({ ...p, apps: p.apps.map((x, j) => (j === i ? { ...x, command: e.target.value } : x)) }))} />
                <Button variant="ghost" className="h-9 w-9 shrink-0 px-0" aria-label={`Remove app ${i + 1}`} onClick={() => edit((p) => ({ ...p, apps: p.apps.filter((_, j) => j !== i) }))}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="space-y-2 border-t border-border pt-4">
        {problems.length > 0 && <Alert tone="warn">{problems.join(" ")}</Alert>}
        {error && <Alert>{error}</Alert>}
        {saved && !dirty && <Alert tone="good">Saved. Your PC has the new rules.</Alert>}
        <div className="flex justify-end gap-2">
          {dirty && <Button variant="ghost" onClick={() => { setDirty(false); if (q.data) setDraft(q.data.policy); }}>Undo changes</Button>}
          <Button onClick={() => save.mutate(draft)} loading={save.isPending} disabled={!dirty || problems.length > 0}>Save rules</Button>
        </div>
      </div>
    </div>
  );
}
