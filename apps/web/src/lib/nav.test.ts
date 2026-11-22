import { describe, expect, it } from "vitest";
import { NAV } from "./nav";

describe("navigation", () => {
  it("has the 13 blueprint sections in order, plus Personal", () => {
    expect(NAV.map((n) => n.label)).toEqual([
      "Home", "AI Assistant", "Calendar", "Tasks", "Projects", "Emails", "Knowledge Base",
      "Finance", "Fitness", "Personal", "Work", "Automations", "Analytics", "Settings",
    ]);
  });
  it("uses unique routes", () => {
    expect(new Set(NAV.map((n) => n.href)).size).toBe(NAV.length);
  });
});
