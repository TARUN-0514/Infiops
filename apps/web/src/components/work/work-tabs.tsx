"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs } from "@/components/life/kit";
import { Boards } from "@/components/security/boards";
import { Findings } from "@/components/security/findings";
import { useWorkspaces } from "@/components/security/hooks";
import { Learning } from "@/components/security/learning";
import { Alert, Skeleton } from "@/components/ui/card";
import { useToday } from "@/lib/today";
import { WorkLogView } from "./work-view";

const TABS = [
  { id: "log", label: "Work log" },
  { id: "ws", label: "Vulnerabilities" },
  { id: "boards", label: "Boards" },
  { id: "learning", label: "Learning" },
] as const;
type Tab = (typeof TABS)[number]["id"];

function Security({ tab, item, board, go }: { tab: "ws" | "boards"; item: string | null; board: string | null; go: (p: Record<string, string | null>) => void }) {
  const q = useWorkspaces();
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError || !q.data) return <Alert>Couldn&apos;t load the workspaces. Check that the API is running.</Alert>;
  const vulns = q.data.find((w) => w.kind === "vulns");
  if (tab === "ws") {
    if (!vulns) return <Alert tone="warn">The vulnerability workspace was deleted. Make a board on the Boards tab instead.</Alert>;
    return <Findings ws={vulns} itemId={item} onOpen={(id) => go({ item: id })} />;
  }
  const boards = q.data.filter((w) => w.kind !== "vulns");
  return <Boards boards={boards} boardId={board} itemId={item} onPick={(id) => go({ board: id, item: null })} onOpen={(id) => go({ item: id })} />;
}

export function WorkTabs() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const today = useToday();
  const raw = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === raw) ? (raw as Tab) : "log";
  const go = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${path}?${next}`, { scroll: false });
  };
  return (
    <div>
      <Tabs label="Work sections" tabs={[...TABS]} value={tab} onChange={(t) => go({ tab: t, item: null })} />
      {tab === "log" && <WorkLogView />}
      {(tab === "ws" || tab === "boards") && <Security tab={tab} item={params.get("item")} board={params.get("board")} go={go} />}
      {tab === "learning" && <Learning today={today} />}
    </div>
  );
}
