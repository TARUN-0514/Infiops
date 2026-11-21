import { describe, expect, it } from "vitest";
import { delta, emptySet, lastDays, monthGrid, summarise, toSets, volume } from "./fitness";

describe("fitness helpers", () => {
  it("turns form rows into sets and skips blank rows", () => {
    const r = toSets([{ ...emptySet("Squat"), reps: "5", weight_kg: "100" }, emptySet(), { ...emptySet("Run"), seconds: "20", distance_km: "3" }]);
    expect(r.error).toBeNull();
    expect(r.sets).toEqual([
      { exercise: "Squat", reps: 5, weight_kg: "100", seconds: null, distance_km: null },
      { exercise: "Run", reps: null, weight_kg: null, seconds: 1200, distance_km: "3" },
    ]);
  });

  it("explains incomplete sets", () => {
    expect(toSets([{ ...emptySet("Squat") , weight_kg: "50" }]).error).toMatch(/reps, time or distance/);
    expect(toSets([{ ...emptySet(), reps: "5" }]).error).toMatch(/needs an exercise/);
    expect(toSets([emptySet()]).error).toMatch(/at least one/);
  });

  it("computes volume and summaries", () => {
    const sets = [
      { exercise: "Bench", reps: 8, weight_kg: "60", seconds: null, distance_km: null },
      { exercise: "Bench", reps: 6, weight_kg: "65", seconds: null, distance_km: null },
      { exercise: "Run", reps: null, weight_kg: null, seconds: 600, distance_km: "1.6" },
    ];
    expect(volume(sets)).toBe(870);
    expect(summarise(sets)).toEqual([
      { exercise: "Bench", text: "8 × 60 kg · 6 × 65 kg" },
      { exercise: "Run", text: "10 min, 1.6 km" },
    ]);
  });

  it("compares weeks", () => {
    expect(delta("80", "81.2")).toEqual({ text: "−1.2", dir: "down" });
    expect(delta(3, 1)).toEqual({ text: "+2", dir: "up" });
    expect(delta(null, "1")).toBeNull();
  });

  it("builds day lists and Monday-first month grids", () => {
    expect(lastDays("2026-03-01", 3)).toEqual(["2026-02-27", "2026-02-28", "2026-03-01"]);
    const nov = Array.from({ length: 30 }, (_, i) => ({ day: `2026-11-${String(i + 1).padStart(2, "0")}`, future: false, spending: 0, workouts: 0, logs: 0 }));
    const grid = monthGrid(nov); // 1 Nov 2026 is a Sunday
    expect(grid.slice(0, 7).filter((x) => x === null)).toHaveLength(6);
    expect(grid[6]?.day).toBe("2026-11-01");
  });
});
