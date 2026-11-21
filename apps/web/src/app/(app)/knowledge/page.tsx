"use client";

import { KnowledgeView } from "@/components/knowledge/knowledge-view";
import { PageHeader } from "@/components/page-header";

export default function KnowledgePage() {
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Knowledge Base" description="Add your files, then search them or ask questions. Answers cite the page they came from." />
      <KnowledgeView />
    </div>
  );
}
