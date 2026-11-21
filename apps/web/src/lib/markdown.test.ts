import { describe, expect, it } from "vitest";
import { parseInline, parseMarkdown } from "./markdown";

describe("markdown subset", () => {
  it("parses lists, code and paragraphs", () => {
    const blocks = parseMarkdown("Here:\n- one\n- **two**\n\n```py\nx = 1\n```\n1. first\n2. second");
    expect(blocks.map((b) => b.kind)).toEqual(["p", "ul", "code", "ol"]);
    const ul = blocks[1];
    expect(ul.kind === "ul" && ul.items[1][0]).toEqual({ kind: "bold", text: "two" });
  });
  it("never produces HTML", () => {
    expect(parseInline("<script>alert(1)</script>")).toEqual([{ kind: "text", text: "<script>alert(1)</script>" }]);
  });
  it("handles inline code and italics", () => {
    expect(parseInline("run `ls` *now*").map((t) => t.kind)).toEqual(["text", "code", "text", "italic"]);
  });
});
