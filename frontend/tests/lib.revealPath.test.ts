import { describe, expect, it } from "vitest";
import { buildIndex } from "../src/lib/indexSchema";
import { collectRevealIds } from "../src/lib/revealPath";
import { smallModel } from "./fixtures/smallModel";

const NS = "{http://example.com/simple}";
const PERSON = `element:${NS}Person`;
const PERSON_TYPE = `complexType:${NS}PersonType`;
const ADDRESS = `element:${NS}PersonType/Address`;
const STREET = `element:${NS}PersonType/Street`;
const ID_ATTR = `attribute:${NS}PersonType/@id`;

describe("collectRevealIds", () => {
  it("expands every ancestor element plus its enclosing named type", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    const ids = collectRevealIds(STREET, indexById, parentById);
    expect(new Set(ids)).toEqual(new Set([PERSON, ADDRESS, PERSON_TYPE]));
    // The target itself is not expanded — revealing must not toggle it open.
    expect(ids).not.toContain(STREET);
  });

  it("expands the host element for an attribute target", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    const ids = collectRevealIds(ID_ATTR, indexById, parentById);
    expect(ids).toContain(PERSON);
    expect(ids).not.toContain(ID_ATTR);
  });

  it("returns nothing for a root element", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    expect(collectRevealIds(PERSON, indexById, parentById)).toEqual([]);
  });

  it("returns nothing when no document path exists (complexType)", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    expect(collectRevealIds(PERSON_TYPE, indexById, parentById)).toEqual([]);
  });
});
