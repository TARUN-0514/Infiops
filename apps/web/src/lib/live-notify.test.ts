import { describe, expect, it } from "vitest";
import { freshNotifications } from "./live-notify";
import type { AppNotification } from "./types";

const n = (id: string, read = false): AppNotification => ({ id, kind: "briefing", title: id, body: "", link: null, read, created_at: "" });

describe("freshNotifications", () => {
  it("ignores what was there on load, then reports new unread ones once", () => {
    let r = freshNotifications(null, [n("a"), n("b")]);
    expect(r.fresh).toEqual([]);
    r = freshNotifications(r.seen, [n("c"), n("d", true), n("a")]);
    expect(r.fresh.map((x) => x.id)).toEqual(["c"]);
    r = freshNotifications(r.seen, [n("c")]);
    expect(r.fresh).toEqual([]);
  });
});
