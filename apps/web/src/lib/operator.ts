import type { AllowedFolder, OperatorPolicy, ResearchFinding } from "@/lib/types";

export const EMPTY_POLICY: OperatorPolicy = {
  enabled: false, apps: [], folders: [], browser: false, screen: false, claude_code: false, paused: false,
};

/** A full Windows (C:\…) or POSIX (/…) path, without "..". Mirrors the server's check. */
export function isFullPath(path: string): boolean {
  const p = path.trim();
  if (!/^[A-Za-z]:[\\/]/.test(p) && !p.startsWith("/")) return false;
  return !p.split(/[\\/]+/).includes("..");
}

/** Problems to fix before saving, in plain words. Empty when the policy is fine. */
export function policyProblems(policy: OperatorPolicy): string[] {
  const out: string[] = [];
  const names = new Set<string>();
  for (const app of policy.apps) {
    const key = app.name.trim().toLowerCase();
    if (!key || !app.command.trim()) out.push("Every app needs a name and a command.");
    else if (names.has(key)) out.push(`Two apps are called “${app.name.trim()}”.`);
    names.add(key);
  }
  for (const f of policy.folders) {
    if (!isFullPath(f.path)) out.push(`“${f.path || "(empty)"}” isn't a full folder path, like C:\\Users\\you\\Documents\\NEXUS.`);
  }
  return [...new Set(out)];
}

/** Writable folders first, then by path. */
export function sortFolders(folders: AllowedFolder[]): AllowedFolder[] {
  return [...folders].sort((a, b) => Number(b.write) - Number(a.write) || a.path.localeCompare(b.path));
}

export const LABEL_TEXT: Record<ResearchFinding["label"], string> = {
  verified: "Verified",
  assumption: "Assumption",
  opinion: "Opinion",
};

export function labelCounts(findings: ResearchFinding[]): Record<ResearchFinding["label"], number> {
  const c = { verified: 0, assumption: 0, opinion: 0 };
  for (const f of findings) c[f.label] += 1;
  return c;
}

/** Splits "text [1] more [2]" into parts so citations can be rendered as links. */
export function citationParts(text: string): (string | number)[] {
  const parts: (string | number)[] = [];
  const re = /\[(\d{1,2})\]/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(Number(m[1]));
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
