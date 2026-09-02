import { describe, expect, it } from "vitest";
import { treeIndentPx } from "../src/components/TreeView/treeIndent";

describe("treeIndentPx", () => {
  it("uses 14px per level on regular viewports", () => {
    expect(treeIndentPx(0, false)).toBe(6);
    expect(treeIndentPx(3, false)).toBe(48);
  });

  it("tightens to 10px per level on compact viewports", () => {
    expect(treeIndentPx(0, true)).toBe(6);
    expect(treeIndentPx(3, true)).toBe(36);
  });
});
