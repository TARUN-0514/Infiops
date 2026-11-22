import { describe, expect, it } from "vitest";
import { daysInMonth, goalProgress, occasion, ordinal, parseTags, weekdaysLabel, whenLabel } from "./personal";

describe("personal helpers", () => {
  it("labels weekdays", () => {
    expect(weekdaysLabel([])).toBe("Every day");
    expect(weekdaysLabel([4, 0, 1, 2, 3])).toBe("Weekdays");
    expect(weekdaysLabel([6, 5])).toBe("Weekends");
    expect(weekdaysLabel([0, 2])).toBe("Mon, Wed");
  });
  it("computes goal progress like the API", () => {
    expect(goalProgress([{ title: "a", done: true }, { title: "b", done: false }, { title: "c", done: false }], 90)).toBe(33);
    expect(goalProgress([], 40)).toBe(40);
  });
  it("says when a date is", () => {
    expect(whenLabel(0)).toBe("Today");
    expect(whenLabel(1)).toBe("Tomorrow");
    expect(whenLabel(5)).toBe("In 5 days");
    expect(whenLabel(7)).toBe("In 1 week");
    expect(whenLabel(90)).toBe("In 3 months");
    expect(whenLabel(null)).toBe("Passed");
  });
  it("names the occasion", () => {
    expect(occasion({ kind: "birthday", turning: 60 })).toBe("Turning 60");
    expect(occasion({ kind: "anniversary", turning: 12 })).toBe("12th anniversary");
    expect(occasion({ kind: "renewal", turning: 3 })).toBe("");
    expect(occasion({ kind: "birthday", turning: null })).toBe("");
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 101].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st"]);
  });
  it("parses tags and month lengths", () => {
    expect(parseTags("#OSCP, work  oscp,, family")).toEqual(["oscp", "work", "family"]);
    expect(daysInMonth(2)).toBe(29);
    expect(daysInMonth(4)).toBe(30);
  });
});
