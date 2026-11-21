"use client";

import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { GoogleIntegration, PushSettings } from "@/components/settings/integrations";

export default function IntegrationsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Integrations" description="Services NEXUS can use. Each shows as connected only after a real test call works.">
        <Link href="/settings" className="text-sm text-accent hover:underline">Back to settings</Link>
      </PageHeader>
      <GoogleIntegration />
      <PushSettings />
    </div>
  );
}
