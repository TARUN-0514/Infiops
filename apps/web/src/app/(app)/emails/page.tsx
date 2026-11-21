"use client";

import { EmailsView } from "@/components/email/emails-view";
import { PageHeader } from "@/components/page-header";

export default function EmailsPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Emails" description="Who is waiting on you, sorted on your PC. Replies go out only after you approve them." />
      <EmailsView />
    </div>
  );
}
