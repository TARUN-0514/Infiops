"use client";

// Learning tracks (OSCP template): syllabus, spaced-repetition reviews, lab and study log.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, Empty, Stat, errorText, inputCls } from "@/components/life/kit";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dayLabel } from "@/lib/calendar";
import { type StudySession, type Topic, type Track, bySection, hours } from "@/lib/workspace";
import { cn } from "@/lib/utils";

function useRefresh() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["learning"] });
}

function NewTrack({ onMade }: { onMade: (id: string) => void }) {
  const refresh = useRefresh();
  const [name, setName] = useState("OSCP");
  const [oscp, setOscp] = useState(true);
  const [target, setTarget] = useState("");
  const make = useMutation({
    mutationFn: () => api<Track>("/learning/tracks", { method: "POST", body: { name: name.trim(), template: oscp ? "oscp" : null, target_date: target || null } }),
    onSuccess: (t) => { refresh(); onMade(t.id); },
  });
  return (
    <Card>
      <CardTitle className="flex items-center gap-2"><GraduationCap className="size-4 text-accent" aria-hidden />Start a learning track</CardTitle>
      <form onSubmit={(e) => { e.preventDefault(); make.mutate(); }} className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">Name<input value={name} onChange={(e) => setName(e.target.value)} className={cn(inputCls, "mt-1 block")} /></label>
        <label className="text-xs text-muted">Exam or target date<input type="date" value={target} onChange={(e) => setTarget(e.target.value)} className={cn(inputCls, "mt-1 block")} /></label>
        <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={oscp} onChange={(e) => setOscp(e.target.checked)} />Start from the OSCP (PEN-200) syllabus</label>
        <Button type="submit" className="h-9" loading={make.isPending} disabled={!name.trim()}>Create</Button>
      </form>
      {make.isError && <div className="mt-2"><Alert>{errorText(make.error)}</Alert></div>}
    </Card>
  );
}

const CONFIDENCE = ["Forgot", "Hard", "Shaky", "OK", "Good", "Easy"];

function Reviews({ topics }: { topics: Topic[] }) {
  const refresh = useRefresh();
  const review = useMutation({ mutationFn: (v: { id: string; confidence: number }) => api(`/learning/topics/${v.id}/review`, { method: "POST", body: { confidence: v.confidence } }), onSuccess: refresh });
  const due = topics.filter((t) => t.due);
  return (
    <Card>
      <CardTitle>Reviews due</CardTitle>
      <p className="mt-1 text-xs text-muted">How well do you remember it? The next review is spaced out by your answer.</p>
      {!due.length ? <div className="mt-3"><Empty>Nothing to review today. Topics you start learning come back here.</Empty></div> : (
        <ul className="mt-3 divide-y divide-border">
          {due.map((t) => (
            <li key={t.id} className="py-2">
              <p className="text-sm">{t.title}<span className="ml-2 text-xs text-muted">{t.section}</span></p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {CONFIDENCE.map((label, i) => (
                  <button key={label} onClick={() => review.mutate({ id: t.id, confidence: i })} disabled={review.isPending} className={cn("rounded-md border border-border px-2 py-1 text-xs hover:bg-raised", i <= 2 ? "text-warn" : "text-good")} aria-label={`${t.title}: ${label}`}>{label}</button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {review.isError && <Alert>{errorText(review.error)}</Alert>}
    </Card>
  );
}

function Syllabus({ track }: { track: Track }) {
  const refresh = useRefresh();
  const [title, setTitle] = useState("");
  const set = useMutation({ mutationFn: (v: { id: string; status: Topic["status"] }) => api(`/learning/topics/${v.id}`, { method: "PATCH", body: { status: v.status } }), onSuccess: refresh });
  const add = useMutation({ mutationFn: () => api(`/learning/tracks/${track.id}/topics`, { method: "POST", body: { title: title.trim(), section: "My topics" } }), onSuccess: () => { setTitle(""); refresh(); } });
  return (
    <Card>
      <CardTitle>Syllabus</CardTitle>
      <div className="mt-3 space-y-4">
        {!track.topics.length && <Empty>No topics yet. Add the ones you want to cover.</Empty>}
        {bySection(track.topics).map(([section, topics]) => {
          const done = topics.filter((t) => t.status === "done").length;
          return (
            <section key={section}>
              <div className="flex items-center justify-between gap-2"><h3 className="text-xs font-medium uppercase tracking-wide text-muted">{section}</h3><span className="text-xs text-muted">{done}/{topics.length}</span></div>
              <ul className="mt-1">
                {topics.map((t) => (
                  <li key={t.id} className="flex items-center gap-2 py-1">
                    <span className={cn("min-w-0 flex-1 text-sm", t.status === "done" && "text-muted line-through")}>{t.title}</span>
                    {t.next_review_on && t.status !== "done" && <span className="hidden text-xs text-muted sm:inline">review {dayLabel(t.next_review_on, { day: "numeric", month: "short" })}</span>}
                    <select aria-label={`${t.title} status`} value={t.status} onChange={(e) => set.mutate({ id: t.id, status: e.target.value as Topic["status"] })} className={cn(inputCls, "h-7 text-xs")}>
                      <option value="todo">To do</option><option value="learning">Learning</option><option value="done">Done</option>
                    </select>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
        <form onSubmit={(e) => { e.preventDefault(); if (title.trim()) add.mutate(); }} className="flex gap-2">
          <input aria-label="New topic" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a topic" className={cn(inputCls, "min-w-0 flex-1")} />
          <Button type="submit" variant="secondary" className="h-9" disabled={!title.trim()} loading={add.isPending}>Add</Button>
        </form>
      </div>
    </Card>
  );
}

const OUTCOME_LABEL: Record<NonNullable<StudySession["outcome"]>, string> = { root: "Rooted", user: "User shell", partial: "Partial", stuck: "Stuck" };

function SessionLog({ track, today }: { track: Track; today: string }) {
  const refresh = useRefresh();
  const [f, setF] = useState({ day: today, kind: "lab" as StudySession["kind"], minutes: "60", machine: "", outcome: "", topic_id: "", notes: "" });
  const add = useMutation({
    mutationFn: () => api(`/learning/tracks/${track.id}/sessions`, { method: "POST", body: { day: f.day, kind: f.kind, minutes: Number(f.minutes), machine: f.machine || null, outcome: f.outcome || null, topic_id: f.topic_id || null, notes: f.notes || null } }),
    onSuccess: () => { setF({ ...f, machine: "", outcome: "", notes: "" }); refresh(); },
  });
  const remove = useMutation({ mutationFn: (id: string) => api(`/learning/sessions/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <Card>
      <CardTitle>Study and lab log</CardTitle>
      <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <input aria-label="Day" type="date" max={today} value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} className={inputCls} />
        <select aria-label="Kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as StudySession["kind"] })} className={inputCls}><option value="lab">Lab</option><option value="study">Study</option><option value="review">Review</option><option value="exam">Practice exam</option></select>
        <input aria-label="Minutes" type="number" min={1} max={1440} value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} className={inputCls} />
        <select aria-label="Topic" value={f.topic_id} onChange={(e) => setF({ ...f, topic_id: e.target.value })} className={inputCls}><option value="">No topic</option>{track.topics.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}</select>
        {f.kind === "lab" && (
          <>
            <input aria-label="Machine" value={f.machine} onChange={(e) => setF({ ...f, machine: e.target.value })} placeholder="Machine" className={inputCls} />
            <select aria-label="Outcome" value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value })} className={inputCls}><option value="">Outcome</option>{Object.entries(OUTCOME_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </>
        )}
        <input aria-label="Notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="What you learned" className={cn(inputCls, f.kind === "lab" ? "col-span-2" : "col-span-2 sm:col-span-4")} />
        <div className="col-span-2 sm:col-span-4"><Button type="submit" className="h-9" loading={add.isPending} disabled={!Number(f.minutes)}>Log session</Button></div>
      </form>
      {add.isError && <div className="mt-2"><Alert>{errorText(add.error)}</Alert></div>}
      {!track.sessions.length ? <div className="mt-3"><Empty>No sessions yet.</Empty></div> : (
        <ul className="mt-3 divide-y divide-border">
          {track.sessions.map((s) => (
            <li key={s.id} className="group flex items-start gap-2 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <p>{s.machine ? `${s.machine}${s.outcome ? ` · ${OUTCOME_LABEL[s.outcome]}` : ""}` : s.topic ?? (s.kind === "exam" ? "Practice exam" : "Study")}</p>
                <p className="text-xs text-muted">{[dayLabel(s.day), hours(s.minutes), s.kind, s.machine ? s.topic : null, s.notes].filter(Boolean).join(" · ")}</p>
              </div>
              <button onClick={() => remove.mutate(s.id)} className="rounded p-1.5 text-muted opacity-100 hover:bg-raised hover:text-danger sm:opacity-0 sm:group-hover:opacity-100" aria-label="Delete session"><Trash2 className="size-3.5" /></button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TrackView({ id, today }: { id: string; today: string }) {
  const q = useQuery({ queryKey: ["learning", "track", id], queryFn: () => api<Track>(`/learning/tracks/${id}`) });
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError || !q.data) return <Alert>Couldn&apos;t load this track.</Alert>;
  const t = q.data;
  const pct = t.stats.topics ? (100 * t.stats.done) / t.stats.topics : 0;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Topics done" value={`${t.stats.done}/${t.stats.topics}`} hint={`${t.stats.learning} in progress`} />
        <Stat label="Reviews due" value={String(t.stats.due_reviews)} tone={t.stats.due_reviews ? "warn" : undefined} />
        <Stat label="This week" value={`${t.stats.hours_week} h`} hint={`${t.stats.hours_total} h in all`} />
        <Stat label="Lab machines" value={String(t.stats.labs)} />
        <Stat label="Rooted" value={String(t.stats.rooted)} tone={t.stats.rooted ? "good" : undefined} />
        <Stat label="Exam" value={t.days_left === null ? "No date" : t.days_left >= 0 ? `${t.days_left} days` : "Passed"} hint={t.target_date ? dayLabel(t.target_date, { day: "numeric", month: "short", year: "numeric" }) : undefined} />
      </div>
      <Bar pct={pct} tone="accent" />
      <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
        <div className="space-y-4"><Reviews topics={t.topics} /><SessionLog track={t} today={today} /></div>
        <Syllabus track={t} />
      </div>
    </div>
  );
}

export function Learning({ today }: { today: string }) {
  const q = useQuery({ queryKey: ["learning", "tracks"], queryFn: () => api<{ id: string; name: string }[]>("/learning/tracks") });
  const [picked, setPicked] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  if (q.isLoading) return <Skeleton className="h-48" />;
  if (q.isError) return <Alert>Couldn&apos;t load learning tracks.</Alert>;
  const tracks = q.data ?? [];
  const current = tracks.find((t) => t.id === picked) ?? tracks[0];
  if (!current || creating) return <NewTrack onMade={(id) => { setPicked(id); setCreating(false); }} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1">
        {tracks.map((t) => <button key={t.id} onClick={() => setPicked(t.id)} className={cn("rounded-lg px-3 py-1.5 text-sm", t.id === current.id ? "bg-raised text-text" : "text-muted hover:bg-raised")}>{t.name}</button>)}
        <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setCreating(true)}>New track</Button>
      </div>
      <TrackView key={current.id} id={current.id} today={today} />
    </div>
  );
}
