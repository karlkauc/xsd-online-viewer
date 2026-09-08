import { describe, expect, it } from "vitest";
import { occursStyle } from "../src/lib/cardinality";

describe("occursStyle", () => {
  it("treats the default 1..1 as mandatory and single", () => {
    expect(occursStyle(1, 1)).toEqual({ optional: false, repeating: false });
  });

  it("flags min 0 as optional", () => {
    expect(occursStyle(0, 1)).toEqual({ optional: true, repeating: false });
  });

  it("flags unbounded as repeating", () => {
    expect(occursStyle(1, "unbounded")).toEqual({ optional: false, repeating: true });
    expect(occursStyle(0, "unbounded")).toEqual({ optional: true, repeating: true });
  });

  it("flags a numeric max above one as repeating", () => {
    expect(occursStyle(2, 5)).toEqual({ optional: false, repeating: true });
    expect(occursStyle(0, 3)).toEqual({ optional: true, repeating: true });
  });

  it("does not treat min above one as optional", () => {
    expect(occursStyle(2, 2)).toEqual({ optional: false, repeating: true });
  });
});
