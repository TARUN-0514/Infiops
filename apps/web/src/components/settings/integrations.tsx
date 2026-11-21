"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CalendarDays, Mail, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { disablePush, enablePush, pushState, type PushState } from "@/lib/push";
import type { ConnectedAccount, Integrations, SyncResult } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

function message(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong. Try again.";
}

const CALLBACK_NOTICE: Record<string, { tone: "good" | "warn" | "danger"; text: string }> = {
  connected: { tone: "good", text: "Google is connected. NEXUS is syncing your mail and calendar now." },
  error: { tone: "warn", text: "Google signed in, but a test call failed. See the details below." },
  failed: { tone: "danger", text: "Connecting Google didn't finish. The link may have expired; try again." },
  cancelled: { tone: "warn", text: "Google sign-in was cancelled." },
};

function SyncLine({ label, icon: Icon, r, tz }: { label: string; icon: typeof Mail; r: SyncResult; tz: string }) {
  return (
    <p className="flex items-center gap-2 text-xs text-muted">
      <Icon className="size-3.5" aria-hidden />
      {label}:{" "}
      {!r ? "not synced yet" : r.status === "failed" ? <span className="text-danger">{r.error}</span> : `${r.items} new or changed · ${formatDateTime(r.at, tz)}`}
    </p>
  );
}

function AccountRow({ a }: { a: ConnectedAccount }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["integrations"] });
    void qc.invalidateQueries({ queryKey: ["email"] });
    void qc.invalidateQueries({ queryKey: ["calendar"] });
  };
  const test = useMutation({ mutationFn: () => api(`/integrations/${a.id}/test`, { method: "POST" }), onSuccess: refresh, onError: (e) => setError(message(e)) });
  const sync = useMutation({ mutationFn: () => api(`/integrations/${a.id}/sync`, { method: "POST" }), onSuccess: refresh, onError: (e) => setError(message(e)) });
  const remove = useMutation({ mutationFn: () => api(`/integrations/${a.id}`, { method: "DELETE" }), onSuccess: refresh, onError: (e) => setError(message(e)) });
  const tz = user?.timezone ?? "UTC";
  const ok = a.status === "connected";
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-medium">
            <span className={cn("inline-block size-2 rounded-full", ok ? "bg-good" : "bg-danger")} aria-hidden />
            {a.account_email}
          </p>
          <p className="mt-0.5 text-xs text-muted">{ok ? "Connected" : "Needs attention"}{a.last_test_at && ` · tested ${formatDateTime(a.last_test_at, tz)}`}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" className="h-8 px-3" onClick={() => sync.mutate()} loading={sync.isPending} disabled={!ok}>
            <RefreshCw className="size-3.5" aria-hidden /> Sync now
          </Button>
          <Button variant="secondary" className="h-8 px-3" onClick={() => test.mutate()} loading={test.isPending}>
            Test
          </Button>
          {confirming ? (
            <Button variant="danger" className="h-8 px-3" onClick={() => remove.mutate()} loading={remove.isPending}>
              Confirm disconnect
            </Button>
          ) : (
            <Button variant="ghost" className="h-8 px-3" onClick={() => setConfirming(true)}>
              Disconnect
            </Button>
          )}
        </div>
      </div>
      {a.last_error && <div className="mt-3"><Alert tone="warn">{a.last_error}</Alert></div>}
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      {confirming && <p className="mt-3 text-xs text-muted">Disconnecting revokes NEXUS&apos;s access and removes the synced copies of your mail and events from NEXUS. Nothing in Google is deleted.</p>}
      <div className="mt-3 space-y-1">
        <SyncLine label="Gmail" icon={Mail} r={a.last_sync.gmail} tz={tz} />
        <SyncLine label="Calendar" icon={CalendarDays} r={a.last_sync.calendar} tz={tz} />
      </div>
      <p className="mt-3 text-xs text-muted">Allowed: {a.permissions.join(" · ") || "none"}</p>
    </div>
  );
}

export function GoogleIntegration() {
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => api<Integrations>("/integrations") });
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("google");
    if (p) {
      setNotice(p);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  const connect = useMutation({
    mutationFn: () => api<{ url: string }>("/integrations/google/start", { method: "POST" }),
    onSuccess: ({ url }) => window.location.assign(url),
    onError: (e) => setError(message(e)),
  });
  const n = notice ? CALLBACK_NOTICE[notice] : null;
  return (
    <Card>
      <CardTitle>Google (Gmail and Calendar)</CardTitle>
      <p className="mt-1 text-sm text-muted">
        NEXUS reads your mail and calendar, writes drafts, and sends an email only after you approve it. Calendar changes made by the assistant also wait for your OK.
      </p>
      {n && <div className="mt-4"><Alert tone={n.tone}>{n.text}</Alert></div>}
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      {q.isLoading ? (
        <Skeleton className="mt-4 h-28" />
      ) : q.isError || !q.data ? (
        <div className="mt-4"><Alert>Couldn&apos;t load integrations.</Alert></div>
      ) : (
        <div className="mt-4 space-y-4">
          {q.data.accounts.map((a) => <AccountRow key={a.id} a={a} />)}
          {!q.data.google.configured ? (
            <div className="rounded-lg border border-dashed border-border p-4 text-sm">
              <p className="font-medium">One-time setup on your PC</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">
                <li>In Google Cloud Console, create a project and enable the Gmail API and Google Calendar API.</li>
                <li>Set up the OAuth consent screen as External, in Testing mode, and add your Gmail address as a test user.</li>
                <li>
                  Create an OAuth client of type Web application with this redirect URI:{" "}
                  <code className="break-all rounded bg-raised px-1 font-mono text-xs">{q.data.google.redirect_uri}</code>
                </li>
                <li>Put the client ID and secret in .env as NEXUS_GOOGLE_CLIENT_ID and NEXUS_GOOGLE_CLIENT_SECRET, then restart with docker compose up -d.</li>
              </ol>
            </div>
          ) : (
            !q.data.accounts.length && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-4">
                <div className="text-sm">
                  <p className="font-medium">Not connected</p>
                  <p className="text-muted">NEXUS will ask Google for: {q.data.google.permissions.join(", ")}.</p>
                </div>
                <Button onClick={() => connect.mutate()} loading={connect.isPending}>Connect Google</Button>
              </div>
            )
          )}
        </div>
      )}
    </Card>
  );
}

const PUSH_TEXT: Record<PushState, string> = {
  unsupported: "This browser can't show push notifications. On iPhone, add NEXUS to your Home Screen first.",
  insecure: "Push needs a secure address. It works at http://localhost on your PC; on your phone it needs HTTPS (for example through Tailscale).",
  denied: "Notifications are blocked for this site. Allow them in your browser's site settings.",
  off: "Get your morning briefing and approvals as notifications on this device.",
  on: "This device gets NEXUS notifications.",
};

export function PushSettings() {
  const [state, setState] = useState<PushState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  useEffect(() => {
    void pushState().then(setState).catch(() => setState("unsupported"));
  }, []);
  const toggle = useMutation({
    mutationFn: () => (state === "on" ? disablePush() : enablePush()),
    onSuccess: (s) => {
      setState(s);
      setError(null);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Couldn't change notifications."),
  });
  const test = useMutation({
    mutationFn: () => api<{ devices: number; delivered: number }>("/push/test", { method: "POST" }),
    onSuccess: (r) => setSent(r.delivered ? "Sent. It should appear in a few seconds." : r.devices ? "The push service didn't accept it. Try turning notifications off and on." : "No device is subscribed yet."),
  });
  return (
    <Card>
      <CardTitle>Notifications on this device</CardTitle>
      {state === null ? <Skeleton className="mt-3 h-10" /> : (
        <div className="mt-2 space-y-3">
          <p className="flex items-start gap-2 text-sm text-muted"><BellRing className="mt-0.5 size-4 shrink-0" aria-hidden />{PUSH_TEXT[state]}</p>
          {error && <Alert>{error}</Alert>}
          {sent && <Alert tone="good">{sent}</Alert>}
          {(state === "on" || state === "off") && (
            <div className="flex gap-2">
              <Button variant={state === "on" ? "secondary" : "primary"} onClick={() => toggle.mutate()} loading={toggle.isPending}>
                {state === "on" ? "Turn off" : "Turn on"}
              </Button>
              {state === "on" && <Button variant="ghost" onClick={() => test.mutate()} loading={test.isPending}>Send a test</Button>}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
