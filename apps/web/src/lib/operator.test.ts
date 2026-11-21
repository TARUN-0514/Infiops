import { describe, expect, it } from "vitest";
import { EMPTY_POLICY, citationParts, isFullPath, labelCounts, policyProblems, sortFolders } from "@/lib/operator";

describe("isFullPath", () => {
  it("accepts Windows and POSIX full paths", () => {
    expect(isFullPath("C:\\Users\\Tarun\\Documents")).toBe(true);
    expect(isFullPath("d:/projects")).toBe(true);
    expect(isFullPath("/home/tarun")).toBe(true);
  });
  it("rejects relative paths and ..", () => {
    expect(isFullPath("Documents")).toBe(false);
    expect(isFullPath("C:\\Users\\..\\Windows")).toBe(false);
    expect(isFullPath("")).toBe(false);
  });
});

describe("policyProblems", () => {
  it("is empty for a good policy", () => {
    expect(policyProblems({ ...EMPTY_POLICY, apps: [{ name: "Notepad", command: "notepad.exe" }], folders: [{ path: "C:\\NEXUS", write: true }] })).toEqual([]);
  });
  it("finds duplicate apps, empty commands and bad folders", () => {
    const p = policyProblems({
      ...EMPTY_POLICY,
      apps: [{ name: "Code", command: "code" }, { name: "code ", command: "x" }, { name: "x", command: " " }],
      folders: [{ path: "Docs", write: false }],
    });
    expect(p).toHaveLength(3);
    expect(p[0]).toContain("Two apps");
    expect(p[2]).toContain("Docs");
  });
});

describe("helpers", () => {
  it("sorts writable folders first", () => {
    expect(sortFolders([{ path: "/b", write: false }, { path: "/a", write: false }, { path: "/z", write: true }]).map((f) => f.path)).toEqual(["/z", "/a", "/b"]);
  });
  it("counts labels", () => {
    expect(labelCounts([{ claim: "a", label: "verified", sources: [1], note: "" }, { claim: "b", label: "opinion", sources: [], note: "" }])).toEqual({ verified: 1, assumption: 0, opinion: 1 });
  });
  it("splits citations", () => {
    expect(citationParts("It has 8 cores [1] and boosts high [2].")).toEqual(["It has 8 cores ", 1, " and boosts high ", 2, "."]);
    expect(citationParts("no cites")).toEqual(["no cites"]);
  });
});
