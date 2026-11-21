import { describe, expect, it } from "vitest";
import { budgetState, dueLabel, money, monthLabel, payoffLabel, shiftMonth, signed } from "./finance";

describe("finance helpers", () => {
  it("formats rupees with Indian grouping", () => {
    expect(money("125000")).toBe("₹1,25,000");
    expect(money("99.5")).toBe("₹99.5");
    expect(money(null)).toBe("–");
    expect(money("abc")).toBe("–");
  });

  it("moves between months across years", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(monthLabel("2026-11")).toMatch(/November 2026/);
  });

  it("colours budgets by how much is used", () => {
    expect(budgetState("500", "1000")).toEqual({ pct: 50, tone: "good" });
    expect(budgetState("850", "1000").tone).toBe("warn");
    expect(budgetState("1200", "1000")).toEqual({ pct: 120, tone: "danger" });
    expect(budgetState("10", null).pct).toBeNull();
  });

  it("labels due dates and payoff times", () => {
    expect(dueLabel(-1)).toBe("Overdue by 1 day");
    expect(dueLabel(0)).toBe("Due today");
    expect(dueLabel(5)).toBe("Due in 5 days");
    expect(dueLabel(null)).toBe("Finished");
    expect(payoffLabel(26)).toBe("2 yrs 2 mo");
    expect(payoffLabel(null)).toMatch(/Never/);
  });

  it("signs amounts by kind", () => {
    expect(signed({ kind: "income", amount: "10" }).text).toBe("+₹10");
    expect(signed({ kind: "expense", amount: "10" }).text).toBe("−₹10");
    expect(signed({ kind: "transfer", amount: "10" }).tone).toBe("muted");
  });
});
