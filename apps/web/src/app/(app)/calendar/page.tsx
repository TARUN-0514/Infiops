"use client";

import { CalendarView } from "@/components/calendar/calendar-view";
import { PageHeader } from "@/components/page-header";

export default function CalendarPage() {
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Calendar" description="Your schedule, conflicts and free time. Click an empty hour to add an event." />
      <CalendarView />
    </div>
  );
}
