"use client";

import { Suspense } from "react";
import { ChatView } from "@/components/assistant/chat-view";
import { SectionTabs } from "@/components/assistant/section-tabs";
import { PageHeader } from "@/components/page-header";

export default function AssistantPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="AI Assistant" description="Chat with NEXUS. It runs on your PC and uses your memory and tools." />
      <SectionTabs />
      <Suspense>
        <ChatView />
      </Suspense>
    </div>
  );
}
