"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { CURRENT_PHASE, NAV } from "@/lib/nav";
import { greetingFor } from "@/lib/utils";

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

export default function HomePage() {
  const { user } = useAuth();
  const now = useNow();
  if (!user) return null;
  const tz = user.timezone;
  const date = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: tz }).format(now);
  const time = new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: tz }).format(now);
  const upcoming = NAV.filter((n) => n.phase > CURRENT_PHASE).sort((a, b) => a.phase - b.phase).slice(0, 4);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="mx-auto max-w-5xl space-y-6">
      <section>
        <p className="text-sm text-muted">{date}</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          {greetingFor(now, tz)}, {user.display_name.split(" ")[0]}.
        </h1>
        <p className="mt-1 font-mono text-sm tabular-nums text-muted" aria-label="Current time">
          {time} · {tz}
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardTitle>Account security</CardTitle>
          {user.mfa_enabled ? (
            <p className="mt-2 text-sm text-muted">Two-factor sign-in is on.</p>
          ) : (
            <p className="mt-2 text-sm text-muted">
              Two-factor sign-in is off. NEXUS will hold your email, calendar and finances, so turn it on now.{" "}
              <Link href="/settings#security" className="text-accent hover:underline">
                Set it up
              </Link>
            </p>
          )}
        </Card>
        <Card>
          <CardTitle>What&apos;s being built next</CardTitle>
          <ul className="mt-2 space-y-1.5 text-sm">
            {upcoming.map((n) => (
              <li key={n.slug} className="flex items-center justify-between gap-3">
                <Link href={n.href} className="text-muted hover:text-text">
                  {n.label}
                </Link>
                <span className="text-xs text-muted">Phase {n.phase}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <p className="text-sm text-muted">
        Your briefing, schedule, tasks and emails appear here as each module ships. Nothing on this page is sample data.
      </p>
    </motion.div>
  );
}
