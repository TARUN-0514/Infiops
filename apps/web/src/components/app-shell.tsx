"use client";

import { AnimatePresence, motion } from "framer-motion";
import { LogOut, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Brand } from "@/components/brand";
import { useAuth } from "@/lib/auth";
import { CURRENT_PHASE, NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="space-y-0.5">
      {NAV.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        const later = item.phase > CURRENT_PHASE;
        return (
          <Link
            key={item.slug}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active ? "bg-accent/15 text-text" : "text-muted hover:bg-raised hover:text-text",
            )}
          >
            <Icon className={cn("size-4 shrink-0", active && "text-accent")} aria-hidden />
            <span className="flex-1 truncate">{item.label}</span>
            {later && (
              <span className="rounded border border-border px-1.5 text-[10px] uppercase tracking-wide text-muted" title={`Arrives in phase ${item.phase}`}>
                P{item.phase}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function UserFooter() {
  const { user, signOut } = useAuth();
  return (
    <div className="flex items-center gap-3 border-t border-border pt-4">
      <div className="grid size-8 place-items-center rounded-full bg-raised text-sm font-semibold" aria-hidden>
        {user?.display_name.slice(0, 1).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{user?.display_name}</p>
        <p className="truncate text-xs text-muted">{user?.email}</p>
      </div>
      <button onClick={() => void signOut()} className="rounded-lg p-2 text-muted hover:bg-raised hover:text-text" aria-label="Sign out" title="Sign out">
        <LogOut className="size-4" />
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-border bg-surface/60 p-4 backdrop-blur lg:flex">
        <Link href="/" className="px-2 pt-1">
          <Brand />
        </Link>
        <div className="flex-1 overflow-y-auto">
          <NavList />
        </div>
        <UserFooter />
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-bg/80 px-4 py-3 backdrop-blur lg:hidden">
        <Brand />
        <button onClick={() => setOpen(true)} className="rounded-lg p-2 text-muted hover:bg-raised" aria-label="Open menu" aria-expanded={open}>
          <Menu className="size-5" />
        </button>
      </header>

      <AnimatePresence>
        {open && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-black/50 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)} />
            <motion.aside
              role="dialog"
              aria-label="Menu"
              className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col gap-6 border-r border-border bg-surface p-4 lg:hidden"
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: "spring", stiffness: 380, damping: 36 }}
            >
              <div className="flex items-center justify-between px-2">
                <Brand />
                <button onClick={() => setOpen(false)} className="rounded-lg p-2 text-muted hover:bg-raised" aria-label="Close menu">
                  <X className="size-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                <NavList onNavigate={() => setOpen(false)} />
              </div>
              <UserFooter />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <main className="min-w-0 px-4 py-6 sm:px-8 lg:py-10">{children}</main>
    </div>
  );
}
