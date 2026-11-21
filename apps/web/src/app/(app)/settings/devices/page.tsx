"use client";

import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { DesktopAppCard, DevicesCard, VoiceStatusCard } from "@/components/settings/devices";

export default function DevicesPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Voice and devices" description="Voice runs on your PC. Nothing you say is sent to the cloud.">
        <Link href="/settings" className="text-sm text-accent hover:underline">Back to settings</Link>
      </PageHeader>
      <VoiceStatusCard />
      <DevicesCard />
      <DesktopAppCard />
    </div>
  );
}
