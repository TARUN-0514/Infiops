import { describe, expect, it } from "vitest";
import { mergeLayout, moveWidget, updateWidget } from "./home-layout";

const DEFS = [
  { id: "briefing", title: "Briefing", size: "m" as const },
  { id: "schedule", title: "Schedule", size: "m" as const },
  { id: "inbox", title: "Inbox", size: "s" as const },
];

describe("home layout", () => {
  it("keeps saved order and adds new widgets at the end", () => {
    const merged = mergeLayout(DEFS, [
      { id: "inbox", size: "l", hidden: true },
      { id: "gone", size: "s", hidden: false },
      { id: "briefing", size: "s", hidden: false },
    ]);
    expect(merged).toEqual([
      { id: "inbox", size: "l", hidden: true },
      { id: "briefing", size: "s", hidden: false },
      { id: "schedule", size: "m", hidden: false },
    ]);
  });

  it("moves and updates widgets", () => {
    const list = mergeLayout(DEFS, []);
    expect(moveWidget(list, 0, 2).map((w) => w.id)).toEqual(["schedule", "inbox", "briefing"]);
    expect(moveWidget(list, 0, 9)).toBe(list);
    expect(updateWidget(list, "inbox", { hidden: true })[2].hidden).toBe(true);
  });
});
