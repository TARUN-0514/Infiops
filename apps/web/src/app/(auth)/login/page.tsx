"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TokenResponse } from "@/lib/types";

export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const tokens = await api<TokenResponse>("/auth/login", {
        method: "POST",
        auth: false,
        body: { email, password, totp_code: needsCode ? code : undefined },
      });
      signIn(tokens);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.code === "mfa_required") {
        setNeedsCode(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div>
        <h1 className="text-lg font-semibold">Sign in</h1>
        <p className="text-sm text-muted">{needsCode ? "Enter the 6-digit code from your authenticator app." : "Welcome back."}</p>
      </div>
      {error && <Alert>{error}</Alert>}
      {!needsCode ? (
        <>
          <Field label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Field label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </>
      ) : (
        <Field
          label="Authentication code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="\d{6}"
          maxLength={6}
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
        />
      )}
      <Button type="submit" className="w-full" loading={loading} disabled={!email || !password || (needsCode && code.length !== 6)}>
        {needsCode ? "Verify" : "Sign in"}
      </Button>
      {needsCode ? (
        <button type="button" className="w-full text-sm text-muted hover:text-text" onClick={() => { setNeedsCode(false); setCode(""); }}>
          Use a different account
        </button>
      ) : (
        <p className="text-center text-sm text-muted">
          First time here?{" "}
          <Link href="/register" className="text-accent hover:underline">
            Create the owner account
          </Link>
        </p>
      )}
    </form>
  );
}
