"use client";

import Link from "next/link";
import { ComputerControl } from "@/components/operator/policy-editor";
import { PageHeader } from "@/components/page-header";

export default function ComputerControlPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Computer control" description="What NEXUS may do on your PC. You can stop it at any time.">
        <Link href="/settings" className="text-sm text-accent hover:underline">Back to settings</Link>
      </PageHeader>
      <ComputerControl />
    </div>
  );
}
