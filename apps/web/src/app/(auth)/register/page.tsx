"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, Skeleton } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TokenResponse } from "@/lib/types";

export default function RegisterPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const status = useQuery({
    queryKey: ["auth-status"],
    queryFn: () => api<{ registration_open: boolean }>("/auth/status", { auth: false }),
  });
  const [form, setForm] = useState({ display_name: "", email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timezone = typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "Asia/Kolkata";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    if (form.password.length < 12) {
      setFieldErrors({ password: "Use at least 12 characters." });
      return;
    }
    setLoading(true);
    try {
      await api("/auth/register", { method: "POST", auth: false, body: { ...form, timezone } });
      const tokens = await api<TokenResponse>("/auth/login", {
        method: "POST",
        auth: false,
        body: { email: form.email, password: form.password },
      });
      signIn(tokens);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(Object.fromEntries(err.fields.map((f) => [f.field, f.message])));
        setError(err.message);
      } else {
        setError("Something went wrong. Try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  if (status.isPending) return <Skeleton className="h-64" />;
  if (status.isError) return <Alert>Can&apos;t reach NEXUS. Check that the API is running.</Alert>;
  if (!status.data.registration_open) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold">Registration is closed</h1>
        <p className="text-sm text-muted">This NEXUS already has an owner account.</p>
        <Link href="/login" className="text-sm text-accent hover:underline">
          Go to sign in
        </Link>
      </div>
    );
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div>
        <h1 className="text-lg font-semibold">Create the owner account</h1>
        <p className="text-sm text-muted">The first account owns this NEXUS. Registration closes after it.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <Field label="Your name" autoComplete="name" required value={form.display_name} onChange={set("display_name")} error={fieldErrors.display_name} />
      <Field label="Email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} error={fieldErrors.email} />
      <Field
        label="Password"
        type="password"
        autoComplete="new-password"
        required
        value={form.password}
        onChange={set("password")}
        error={fieldErrors.password}
        hint="At least 12 characters. A short sentence works well."
      />
      <Button type="submit" className="w-full" loading={loading} disabled={!form.display_name || !form.email || !form.password}>
        Create account
      </Button>
    </form>
  );
}
