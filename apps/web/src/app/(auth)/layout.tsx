"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Brand } from "@/components/brand";
import { useAuth } from "@/lib/auth";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (status === "signed-in") router.replace("/");
  }, [status, router]);

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex justify-center">
          <Brand size="lg" />
        </div>
        <div className="rounded-xl border border-border bg-surface/80 p-6 shadow-2xl shadow-black/20 backdrop-blur">
          {children}
        </div>
      </div>
    </main>
  );
}
