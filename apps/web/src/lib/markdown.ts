/** A small, safe markdown subset for assistant replies: paragraphs, headings, lists,
 * fenced code, inline code, bold and italics. Produces tokens, never raw HTML. */

export type Inline = { kind: "text" | "code" | "bold" | "italic"; text: string };
export type Block =
  | { kind: "p"; inline: Inline[] }
  | { kind: "h"; level: number; inline: Inline[] }
  | { kind: "ul" | "ol"; items: Inline[][] }
  | { kind: "code"; lang: string; text: string };

export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (const m of src.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push({ kind: "text", text: src.slice(last, idx) });
    const tok = m[0];
    if (tok.startsWith("`")) out.push({ kind: "code", text: tok.slice(1, -1) });
    else if (tok.startsWith("**")) out.push({ kind: "bold", text: tok.slice(2, -2) });
    else out.push({ kind: "italic", text: tok.slice(1, -1) });
    last = idx + tok.length;
  }
  if (last < src.length) out.push({ kind: "text", text: src.slice(last) });
  return out;
}

export function parseMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "p", inline: parseInline(para.join(" ")) });
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(/^```(\w*)/);
    if (fence) {
      flush();
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      blocks.push({ kind: "code", lang: fence[1], text: body.join("\n") });
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)/);
    if (heading) {
      flush();
      blocks.push({ kind: "h", level: heading[1].length, inline: parseInline(heading[2]) });
      continue;
    }
    const bullet = line.match(/^\s*[-*•]\s+(.*)/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (bullet || numbered) {
      flush();
      const kind = bullet ? "ul" : "ol";
      const prev = blocks[blocks.length - 1];
      const item = parseInline((bullet ?? numbered)![1]);
      if (prev && prev.kind === kind) prev.items.push(item);
      else blocks.push({ kind, items: [item] });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    para.push(line.trim());
  }
  flush();
  return blocks;
}
