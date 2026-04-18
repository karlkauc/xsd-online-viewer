import { describe, expect, it } from "vitest";
import { collectExpandableElementIds } from "../src/lib/expandAll";
import { smallModel } from "./fixtures/smallModel";

describe("collectExpandableElementIds", () => {
  it("includes every element with a resolvable complex type", () => {
    const ids = collectExpandableElementIds(smallModel);
    // Person → PersonType (resolvable); Address → inline complex type.
    expect(ids.has("element:{http://example.com/simple}Person")).toBe(true);
    expect(ids.has("element:{http://example.com/simple}PersonType/Address")).toBe(true);
  });

  it("excludes leaf elements whose type is a simpleType or xs:*", () => {
    const ids = collectExpandableElementIds(smallModel);
    // FirstName → xs:string, no expansion; Age → tns:AgeType (simple).
    expect(ids.has("element:{http://example.com/simple}PersonType/FirstName")).toBe(false);
    expect(ids.has("element:{http://example.com/simple}PersonType/Age")).toBe(false);
    expect(ids.has("element:{http://example.com/simple}PersonType/Color")).toBe(false);
  });
});
