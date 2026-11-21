import { notFound } from "next/navigation";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { CURRENT_PHASE, NAV, findNav } from "@/lib/nav";

export function generateStaticParams() {
  return NAV.filter((n) => n.phase > CURRENT_PHASE).map((n) => ({ module: n.slug }));
}

export const dynamicParams = false;

export default async function ModulePage({ params }: { params: Promise<{ module: string }> }) {
  const { module } = await params;
  const item = findNav(module);
  if (!item || item.phase <= CURRENT_PHASE) notFound();
  const Icon = item.icon;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={item.label} description={item.summary} />
      <Card className="flex flex-col items-center gap-4 py-12 text-center">
        <div className="grid size-12 place-items-center rounded-xl bg-accent/15 text-accent">
          <Icon className="size-6" aria-hidden />
        </div>
        <div>
          <p className="font-medium">Arrives in phase {item.phase}</p>
          <p className="mt-1 text-sm text-muted">This module isn&apos;t built yet. When it ships, it will include:</p>
        </div>
        <ul className="space-y-1 text-sm text-muted">
          {item.coming.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
