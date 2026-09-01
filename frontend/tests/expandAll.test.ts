import { describe, expect, it } from "vitest";
import { collectExpandableElementIds } from "../src/lib/expandAll";
import { smallModel } from "./fixtures/smallModel";
import { refModel, DOCUMENT_ID, SIGNATURE_REF_ID } from "./fixtures/refModel";

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

describe("collectExpandableElementIds with references", () => {
  it("marks a ref particle expandable via the declaration it points at", () => {
    const ids = collectExpandableElementIds(refModel);
    expect(ids.has(DOCUMENT_ID)).toBe(true);
    expect(ids.has(SIGNATURE_REF_ID)).toBe(true);
  });
});
