"use client";

import { useAuth } from "@/lib/auth";
import { dayKey } from "@/lib/calendar";

/** Today's date (YYYY-MM-DD) in the owner's own time zone. */
export function useToday(): string {
  const { user } = useAuth();
  return dayKey(new Date(), user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone);
}
