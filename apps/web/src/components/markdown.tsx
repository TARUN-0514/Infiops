import { Fragment } from "react";
import { parseMarkdown, type Inline } from "@/lib/markdown";

function Inlines({ items }: { items: Inline[] }) {
  return (
    <>
      {items.map((t, i) =>
        t.kind === "code" ? (
          <code key={i} className="rounded bg-raised px-1 py-0.5 font-mono text-[0.85em]">{t.text}</code>
        ) : t.kind === "bold" ? (
          <strong key={i} className="font-semibold">{t.text}</strong>
        ) : t.kind === "italic" ? (
          <em key={i}>{t.text}</em>
        ) : (
          <Fragment key={i}>{t.text}</Fragment>
        ),
      )}
    </>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {parseMarkdown(text).map((b, i) => {
        if (b.kind === "p") return <p key={i}><Inlines items={b.inline} /></p>;
        if (b.kind === "h") return <p key={i} className="font-semibold"><Inlines items={b.inline} /></p>;
        if (b.kind === "code")
          return (
            <pre key={i} className="overflow-x-auto rounded-lg border border-border bg-bg p-3 font-mono text-xs">
              <code>{b.text}</code>
            </pre>
          );
        const List = b.kind === "ul" ? "ul" : "ol";
        return (
          <List key={i} className={b.kind === "ul" ? "list-disc space-y-1 pl-5" : "list-decimal space-y-1 pl-5"}>
            {b.items.map((it, j) => <li key={j}><Inlines items={it} /></li>)}
          </List>
        );
      })}
    </div>
  );
}
