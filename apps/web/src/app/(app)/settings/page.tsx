"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Monitor, Moon, Sun } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { AiStatusCard, MemoryConsent, ToolPermissions } from "@/components/settings/ai-settings";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardTitle, Skeleton } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { applyTheme, readThemeChoice, type ThemeChoice } from "@/lib/theme";
import type { MfaSetup, SessionInfo, User } from "@/lib/types";
import { cn, describeUserAgent, formatDateTime } from "@/lib/utils";

function message(err: unknown) {
  return err instanceof ApiError ? err.message : "Something went wrong. Try again.";
}

function Appearance() {
  const [choice, setChoice] = useState<ThemeChoice>("dark");
  useEffect(() => setChoice(readThemeChoice()), []);
  const options: { value: ThemeChoice; label: string; icon: typeof Moon }[] = [
    { value: "dark", label: "Dark", icon: Moon },
    { value: "light", label: "Light", icon: Sun },
    { value: "system", label: "System", icon: Monitor },
  ];
  return (
    <Card>
      <CardTitle>Appearance</CardTitle>
      <div role="radiogroup" aria-label="Theme" className="mt-4 grid grid-cols-3 gap-2 sm:max-w-sm">
        {options.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            role="radio"
            aria-checked={choice === value}
            onClick={() => {
              setChoice(value);
              applyTheme(value);
            }}
            className={cn(
              "flex flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-sm",
              choice === value ? "border-accent bg-accent/10 text-text" : "border-border text-muted hover:text-text",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>
    </Card>
  );
}

function TwoFactor() {
  const { user, setUser } = useAuth();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: () => api<MfaSetup>("/auth/mfa/setup", { method: "POST" }),
    onSuccess: async (data) => {
      setSetup(data);
      setQr(await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 200 }));
    },
  });
  const enable = useMutation({
    mutationFn: () => api<User>("/auth/mfa/enable", { method: "POST", body: { code } }),
    onSuccess: (u) => {
      setUser(u);
      setSetup(null);
      setCode("");
      setNotice("Two-factor sign-in is on.");
    },
  });
  const disable = useMutation({
    mutationFn: () => api<User>("/auth/mfa/disable", { method: "POST", body: { code } }),
    onSuccess: (u) => {
      setUser(u);
      setCode("");
      setNotice("Two-factor sign-in is off.");
    },
  });
  const err = start.error ?? enable.error ?? disable.error;

  return (
    <Card id="security">
      <CardTitle>Two-factor sign-in</CardTitle>
      <p className="mt-1 text-sm text-muted">Use an authenticator app such as Google Authenticator, 1Password or Authy.</p>
      <div className="mt-4 space-y-4">
        {notice && <Alert tone="good">{notice}</Alert>}
        {err && <Alert>{message(err)}</Alert>}
        {user?.mfa_enabled ? (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              disable.mutate();
            }}
          >
            <div className="w-40">
              <Field label="Current code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            </div>
            <Button type="submit" variant="danger" loading={disable.isPending} disabled={code.length !== 6}>
              Turn off
            </Button>
          </form>
        ) : setup ? (
          <div className="flex flex-col gap-5 sm:flex-row">
            {qr && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr} alt="QR code to add NEXUS to your authenticator app" className="size-[200px] rounded-lg bg-white p-2" />
            )}
            <form
              className="flex-1 space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                enable.mutate();
              }}
            >
              <p className="text-sm text-muted">Scan the code, or enter this key by hand:</p>
              <code className="block break-all rounded-lg bg-raised px-3 py-2 font-mono text-sm">{setup.secret}</code>
              <Field label="Code from the app" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
              <Button type="submit" loading={enable.isPending} disabled={code.length !== 6}>
                Turn on
              </Button>
            </form>
          </div>
        ) : (
          <Button onClick={() => start.mutate()} loading={start.isPending}>
            Set up two-factor sign-in
          </Button>
        )}
      </div>
    </Card>
  );
}

function Sessions() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionInfo[]>("/auth/sessions") });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/auth/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const tz = user?.timezone ?? "Asia/Kolkata";

  return (
    <Card>
      <CardTitle>Signed-in devices</CardTitle>
      <div className="mt-4 space-y-2">
        {sessions.isPending && <Skeleton className="h-14" />}
        {sessions.isError && <Alert>{message(sessions.error)}</Alert>}
        {revoke.isError && <Alert>{message(revoke.error)}</Alert>}
        {sessions.data?.map((s) => (
          <div key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {describeUserAgent(s.user_agent)}
                {s.current && <span className="ml-2 rounded bg-good/15 px-1.5 py-0.5 text-xs text-good">This device</span>}
              </p>
              <p className="text-xs text-muted">
                Last active {formatDateTime(s.last_used_at, tz)}
                {s.ip ? ` · ${s.ip}` : ""}
              </p>
            </div>
            {!s.current && (
              <Button variant="secondary" className="h-8 px-3" loading={revoke.isPending && revoke.variables === s.id} onClick={() => revoke.mutate(s.id)}>
                Sign out
              </Button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Settings" description="Profile, appearance, AI, memory and security." />
      <div className="space-y-4">
        <Card>
          <CardTitle>Profile</CardTitle>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted">Name</dt>
              <dd>{user?.display_name}</dd>
            </div>
            <div>
              <dt className="text-muted">Email</dt>
              <dd className="break-all">{user?.email}</dd>
            </div>
            <div>
              <dt className="text-muted">Time zone</dt>
              <dd>{user?.timezone}</dd>
            </div>
          </dl>
        </Card>
        <Appearance />
        <AiStatusCard />
        <ToolPermissions />
        <MemoryConsent />
        <TwoFactor />
        <Sessions />
      </div>
    </div>
  );
}
