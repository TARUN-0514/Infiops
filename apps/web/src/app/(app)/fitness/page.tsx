"use client";

import { Suspense } from "react";
import { FitnessView } from "@/components/fitness/fitness-view";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/card";

export default function FitnessPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Fitness" description="Workouts, body measurements, food, water, sleep and habits. Encrypted, local model only, and for tracking, not medical advice." />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <FitnessView />
      </Suspense>
    </div>
  );
}
