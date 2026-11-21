"use client";

import { useMutation } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type ImportMapping, type ImportPreview, ROLE_LABEL, money } from "@/lib/finance";
import { cn } from "@/lib/utils";
import { useAccounts, useRefreshFinance } from "./hooks";

const ROLES = ["date", "description", "amount", "debit", "credit", "drcr"] as const;

function form(file: File, mapping: ImportMapping | null, accountId?: string) {
  const f = new FormData();
  f.append("file", file);
  if (mapping) f.append("mapping", JSON.stringify(mapping));
  if (accountId) f.append("account_id", accountId);
  return f;
}

function MappingPicker({ header, mapping, onChange }: { header: string[]; mapping: ImportMapping; onChange: (m: ImportMapping) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {ROLES.map((role) => (
        <label key={role} className="text-sm">
          {ROLE_LABEL[role]}
          <select
            aria-label={ROLE_LABEL[role]}
            value={mapping[role] ?? ""}
            onChange={(e) => onChange({ ...mapping, [role]: e.target.value === "" ? null : Number(e.target.value) })}
            className={cn(inputCls, "mt-1 w-full")}
          >
            <option value="">{role === "date" || role === "description" ? "Pick a column" : "Not used"}</option>
            {header.map((h, i) => <option key={i} value={i}>{h || `Column ${i + 1}`}</option>)}
          </select>
        </label>
      ))}
      <label className="flex items-center gap-2 text-sm sm:col-span-3">
        <input type="checkbox" checked={mapping.day_first} onChange={(e) => onChange({ ...mapping, day_first: e.target.checked })} />
        Dates are day first (31/12/2026)
      </label>
    </div>
  );
}

export function Import() {
  const accounts = useAccounts();
  const refresh = useRefreshFinance();
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [accountId, setAccountId] = useState("");
  const [result, setResult] = useState<{ added: number; duplicates: number } | null>(null);
  const preview = useMutation({
    mutationFn: (args: { f: File; m: ImportMapping | null }) => api<ImportPreview>("/finance/import/preview", { method: "POST", form: form(args.f, args.m) }),
    onSuccess: (p) => setMapping(p.mapping ?? { date: 0, description: 1, amount: null, debit: null, credit: null, drcr: null, day_first: true }),
  });
  const run = useMutation({
    mutationFn: () => api<{ added: number; duplicates: number }>("/finance/import", { method: "POST", form: form(file as File, mapping, accountId) }),
    onSuccess: (r) => { setResult(r); setFile(null); preview.reset(); setMapping(null); refresh(); },
  });
  const p = preview.data;
  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Import a bank statement</CardTitle>
        <p className="mt-1 text-sm text-muted">Download a CSV from your bank or card and drop it here. NEXUS finds the columns, skips rows it already has, and keeps everything on this server.</p>
        <label className="mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-border px-4 py-6 text-sm text-muted hover:bg-raised/50">
          <FileUp className="size-5" />
          <span>{file ? file.name : "Choose a .csv file (up to 5 MB)"}</span>
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              setResult(null);
              setMapping(null);
              if (f) preview.mutate({ f, m: null });
              e.target.value = ""; // so choosing the same file again still triggers a read
            }}
          />
        </label>
        {preview.isPending && <p className="mt-3 text-sm text-muted" role="status">Reading the file…</p>}
        {preview.isError && <div className="mt-3"><Alert>{errorText(preview.error)}</Alert></div>}
        {result && <div className="mt-3"><Alert tone="good">Imported {result.added} entr{result.added === 1 ? "y" : "ies"}{result.duplicates ? `, skipped ${result.duplicates} already there` : ""}.</Alert></div>}
      </Card>

      {p && file && mapping && (
        <Card>
          <CardTitle>Check before importing</CardTitle>
          {p.errors.length > 0 && <div className="mt-3"><Alert tone="warn">{p.errors.slice(0, 5).map((e) => <div key={e}>{e}</div>)}{p.errors.length > 5 && <div>…and {p.errors.length - 5} more.</div>}</Alert></div>}
          <details className="mt-3" open={!p.mapping}>
            <summary className="cursor-pointer text-sm text-muted">Columns</summary>
            <div className="mt-3 space-y-2">
              <MappingPicker header={p.header} mapping={mapping} onChange={setMapping} />
              <Button variant="secondary" className="h-9" loading={preview.isPending} onClick={() => preview.mutate({ f: file, m: mapping })}>Read again with these columns</Button>
            </div>
          </details>
          {p.total > 0 && (
            <>
              <p className="mt-4 text-sm">
                {p.total} rows: {money(p.expense)} out, {money(p.income)} in.
                {p.duplicates > 0 && <span className="text-muted"> {p.duplicates} already imported and will be skipped.</span>}
              </p>
              <div className="mt-3 max-h-96 overflow-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-surface text-left text-xs text-muted">
                    <tr><th className="p-2 font-medium">Date</th><th className="p-2 font-medium">Description</th><th className="p-2 font-medium">Category</th><th className="p-2 text-right font-medium">Amount</th></tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {p.rows.map((r, i) => (
                      <tr key={i} className={cn(r.duplicate && "text-muted line-through")}>
                        <td className="whitespace-nowrap p-2">{dayLabel(r.occurred_on, { day: "numeric", month: "short" })}</td>
                        <td className="max-w-56 truncate p-2">{r.description}</td>
                        <td className="p-2">{r.category}</td>
                        <td className={cn("whitespace-nowrap p-2 text-right tabular-nums", r.kind === "income" && !r.duplicate && "text-good")}>{r.kind === "income" ? "+" : "−"}{money(r.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {p.total > p.rows.length && <p className="mt-1 text-xs text-muted">Showing the first {p.rows.length}.</p>}
            </>
          )}
          {p.total === 0 && p.mapping && <div className="mt-3"><Empty>No rows with an amount were found.</Empty></div>}
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <label className="text-sm">Into account
              <select aria-label="Into account" value={accountId} onChange={(e) => setAccountId(e.target.value)} className={cn(inputCls, "mt-1 block")}>
                <option value="">No account</option>
                {accounts.data?.filter((a) => !a.archived).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <Button className="h-9" loading={run.isPending} disabled={!p.mapping || p.total - p.duplicates <= 0} onClick={() => run.mutate()}>
              Import {Math.max(0, p.total - p.duplicates)} entries
            </Button>
          </div>
          {run.isError && <div className="mt-3"><Alert>{errorText(run.error)}</Alert></div>}
        </Card>
      )}
    </div>
  );
}
