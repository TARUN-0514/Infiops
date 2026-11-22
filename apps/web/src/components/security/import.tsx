"use client";

import { useMutation } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { useState } from "react";
import { errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { SOURCES, SOURCE_LABEL, type ImportPreview, type ImportResult, type Workspace } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import { SeverityBadge } from "./badges";
import { useRefreshWs } from "./hooks";

const HINT: Record<string, string> = {
  inspector: "Inspector findings export (JSON) or CSV.",
  ghas: "Output of gh api repos/OWNER/REPO/code-scanning/alerts (or dependabot or secret-scanning alerts), as JSON.",
  dast: "CSV from your DAST scanner with a title or name column.",
  guardium: "CSV from a Guardium vulnerability assessment report.",
  pentest: "CSV of pentest findings.",
  manual: "Any CSV with a title column.",
};

function body(file: File, source: string, dry: boolean) {
  const f = new FormData();
  f.append("file", file);
  f.append("source", source);
  f.append("dry_run", String(dry));
  return f;
}

export function ImportFindings({ ws }: { ws: Workspace }) {
  const refresh = useRefreshWs();
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("inspector");
  const [result, setResult] = useState<ImportResult | null>(null);
  const preview = useMutation({ mutationFn: (f: File) => api<ImportPreview>(`/workspaces/${ws.id}/import`, { method: "POST", form: body(f, source, true) }) });
  const run = useMutation({
    mutationFn: (f: File) => api<ImportResult>(`/workspaces/${ws.id}/import`, { method: "POST", form: body(f, source, false) }),
    onSuccess: (r) => { setResult(r); setFile(null); preview.reset(); refresh(); },
  });
  return (
    <Card>
      <CardTitle className="flex items-center gap-2"><FileUp className="size-4 text-accent" aria-hidden />Import findings</CardTitle>
      <p className="mt-1 text-xs text-muted">Re-import the same export any time: new findings are added, ones the scanner now reports fixed are closed, and ones that come back are reopened.</p>
      <div className="mt-3 space-y-2">
        <select aria-label="Import source" value={source} onChange={(e) => { setSource(e.target.value); preview.reset(); }} className={cn(inputCls, "w-full")}>
          {SOURCES.filter((s) => s !== "manual").map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
        </select>
        <p className="text-xs text-muted">{HINT[source]}</p>
        <input
          aria-label="Findings file"
          type="file"
          accept=".json,.csv,.tsv,.txt"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            e.target.value = "";
            setFile(f);
            setResult(null);
            if (f) preview.mutate(f);
          }}
          className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-raised file:px-3 file:py-1.5 file:text-text"
        />
      </div>
      {preview.isPending && <p className="mt-3 text-sm text-muted">Reading the file…</p>}
      {preview.isError && <div className="mt-3"><Alert>{errorText(preview.error)}</Alert></div>}
      {preview.data && file && (
        <div className="mt-3 space-y-2">
          <p className="text-sm">{file.name}: {preview.data.rows} rows, {preview.data.open} open.</p>
          {preview.data.errors.length > 0 && <Alert tone="warn">{preview.data.errors.join(" ")}</Alert>}
          <ul className="max-h-48 divide-y divide-border overflow-y-auto text-xs">
            {preview.data.sample.map((r, i) => (
              <li key={i} className={cn("flex items-center gap-2 py-1.5", r.fixed && "opacity-50")}><SeverityBadge s={r.severity} /><span className="min-w-0 flex-1 truncate">{r.title}</span>{r.fixed && <span className="text-muted">fixed</span>}</li>
            ))}
          </ul>
          <Button className="h-8" onClick={() => run.mutate(file)} loading={run.isPending} disabled={preview.data.rows === 0}>Import {preview.data.rows} rows</Button>
          {run.isError && <Alert>{errorText(run.error)}</Alert>}
        </div>
      )}
      {result && <div className="mt-3"><Alert tone="good">Added {result.added}, updated {result.updated}, unchanged {result.unchanged}.</Alert></div>}
    </Card>
  );
}
