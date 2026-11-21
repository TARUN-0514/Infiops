import { describe, expect, it } from "vitest";
import { parseNdjson } from "./stream";

describe("parseNdjson", () => {
  it("returns complete events and keeps the partial line", () => {
    const { events, rest } = parseNdjson('{"type":"text.delta","text":"Hi"}\n{"type":"text.de');
    expect(events).toEqual([{ type: "text.delta", text: "Hi" }]);
    expect(rest).toBe('{"type":"text.de');
  });
  it("skips blank and malformed lines", () => {
    const { events } = parseNdjson('\nnot json\n{"type":"run.finished","run_id":"r","status":"completed"}\n');
    expect(events).toHaveLength(1);
  });
});
