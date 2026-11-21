"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { AppShell } from "@/components/app-shell";
import { Brand } from "@/components/brand";
import { useAuth } from "@/lib/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (status === "signed-out") router.replace("/login");
  }, [status, router]);

  if (status !== "signed-in") {
    return (
      <div className="grid min-h-dvh place-items-center" aria-busy="true" aria-live="polite">
        <div className="animate-pulse">
          <Brand size="lg" />
        </div>
      </div>
    );
  }
  return <AppShell>{children}</AppShell>;
}
