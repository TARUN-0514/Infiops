"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Check, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Empty, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { LIST_KINDS, type PersonalList } from "@/lib/personal";
import { cn } from "@/lib/utils";
import { useRefreshPersonal } from "./hooks";

const KIND_LABEL: Record<PersonalList["kind"], string> = { checklist: "Checklist", shopping: "Shopping", reading: "Reading", travel: "Travel", ideas: "Ideas" };

function ListCard({ l }: { l: PersonalList }) {
  const refresh = useRefreshPersonal("lists");
  const [text, setText] = useState("");
  const add = useMutation({ mutationFn: () => api(`/lists/${l.id}/items`, { method: "POST", body: { text: text.trim() } }), onSuccess: () => { setText(""); refresh(); } });
  const tick = useMutation({ mutationFn: (v: { id: string; done: boolean }) => api(`/list-items/${v.id}`, { method: "PATCH", body: { done: v.done } }), onSuccess: refresh });
  const drop = useMutation({ mutationFn: (id: string) => api(`/list-items/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const archive = useMutation({ mutationFn: () => api(`/lists/${l.id}`, { method: "PUT", body: { name: l.name, kind: l.kind, archived: !l.archived } }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => api(`/lists/${l.id}`, { method: "DELETE" }), onSuccess: refresh });
  const done = l.items.filter((i) => i.done).length;
  return (
    <Card className={cn("flex flex-col", l.archived && "opacity-60")}>
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1"><CardTitle className="truncate">{l.name}</CardTitle><p className="text-xs text-muted">{KIND_LABEL[l.kind]} · {done}/{l.items.length} done</p></div>
        <button onClick={() => archive.mutate()} className="rounded p-1.5 text-muted hover:bg-raised" aria-label={l.archived ? `Restore ${l.name}` : `Archive ${l.name}`}>{l.archived ? <ArchiveRestore className="size-3.5" /> : <Archive className="size-3.5" />}</button>
        <button onClick={() => remove.mutate()} className="rounded p-1.5 text-muted hover:bg-raised hover:text-danger" aria-label={`Delete ${l.name}`}><Trash2 className="size-3.5" /></button>
      </div>
      <ul className="mt-3 space-y-1">
        {l.items.map((i) => (
          <li key={i.id} className="group flex items-center gap-2 text-sm">
            <button onClick={() => tick.mutate({ id: i.id, done: !i.done })} aria-pressed={i.done} aria-label={`${i.text} done`} className={cn("flex size-5 shrink-0 items-center justify-center rounded border", i.done ? "border-good/50 bg-good/20 text-good" : "border-border")}>{i.done && <Check className="size-3" />}</button>
            <span className={cn("min-w-0 flex-1 break-words", i.done && "text-muted line-through")}>{i.text}</span>
            <button onClick={() => drop.mutate(i.id)} className="text-muted opacity-100 hover:text-danger sm:opacity-0 sm:group-hover:opacity-100" aria-label={`Remove ${i.text}`}><X className="size-3.5" /></button>
          </li>
        ))}
      </ul>
      {!l.archived && (
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate(); }} className="mt-2">
          <input aria-label={`Add to ${l.name}`} value={text} onChange={(e) => setText(e.target.value)} placeholder="+ Add an item" className={cn(inputCls, "h-8 w-full bg-transparent")} />
        </form>
      )}
      {add.isError && <p className="mt-1 text-xs text-danger">{errorText(add.error)}</p>}
    </Card>
  );
}

export function Lists() {
  const refresh = useRefreshPersonal("lists");
  const q = useQuery({ queryKey: ["personal", "lists"], queryFn: () => api<PersonalList[]>("/lists") });
  const [name, setName] = useState("");
  const [kind, setKind] = useState<PersonalList["kind"]>("checklist");
  const make = useMutation({ mutationFn: () => api("/lists", { method: "POST", body: { name: name.trim(), kind } }), onSuccess: () => { setName(""); refresh(); } });
  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); make.mutate(); }} className="flex flex-wrap gap-2">
        <input aria-label="List name" value={name} onChange={(e) => setName(e.target.value)} placeholder="New list, e.g. Groceries" className={cn(inputCls, "min-w-0 flex-1 basis-48")} />
        <select aria-label="List kind" value={kind} onChange={(e) => setKind(e.target.value as PersonalList["kind"])} className={inputCls}>{LIST_KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}</select>
        <Button type="submit" className="h-9" loading={make.isPending} disabled={!name.trim()}>Make list</Button>
      </form>
      {make.isError && <Alert>{errorText(make.error)}</Alert>}
      {q.isLoading ? <Skeleton className="h-40" /> : q.isError ? <Alert>Couldn&apos;t load lists.</Alert> : !q.data?.length ? <Empty>No lists yet. You can also say “add milk to groceries” in chat once a list exists.</Empty> : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{q.data.map((l) => <ListCard key={l.id} l={l} />)}</div>
      )}
    </div>
  );
}
