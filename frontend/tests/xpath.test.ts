import { describe, expect, it } from "vitest";
import { buildIndex } from "../src/lib/indexSchema";
import { computeXPath } from "../src/lib/xpath";
import { smallModel } from "./fixtures/smallModel";
import type { NodeIndexEntry } from "../src/types/schema";

function labels(segs: ReturnType<typeof computeXPath>): string[] {
  return (segs ?? []).map((s) => s.label);
}

describe("computeXPath", () => {
  it("returns null when no selection", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    expect(computeXPath(null, indexById, parentById)).toBeNull();
  });

  it("walks through a named complexType back to its referencing element", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    const firstName = Array.from(indexById.values()).find(
      (e) => e.kind === "element" && e.label === "FirstName",
    )!;
    const path = computeXPath(firstName.id, indexById, parentById);
    expect(labels(path)).toEqual(["Person", "FirstName"]);
  });

  it("treats inline anonymous complexTypes transparently", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    const street = Array.from(indexById.values()).find(
      (e) => e.kind === "element" && e.label === "Street",
    )!;
    const path = computeXPath(street.id, indexById, parentById);
    expect(labels(path)).toEqual(["Person", "Address", "Street"]);
  });

  it("appends attribute segments with an @ prefix", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    const idAttr = Array.from(indexById.values()).find(
      (e) => e.kind === "attribute" && e.label === "id",
    )!;
    const path = computeXPath(idAttr.id, indexById, parentById);
    expect(labels(path)).toEqual(["Person", "@id"]);
    expect(path?.at(-1)?.isAttribute).toBe(true);
  });

  it("returns null for top-level types without a document path", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    const ageType = Array.from(indexById.values()).find(
      (e) => e.kind === "simpleType" && e.label === "AgeType",
    )!;
    // simpleType selections never produce a meaningful XPath.
    expect(computeXPath(ageType.id, indexById, parentById)).toBeNull();

    const personType = Array.from(indexById.values()).find(
      (e) => e.kind === "complexType" && e.label === "PersonType",
    )!;
    // complexType selections are also hidden — the XPath bar only shows for
    // element/attribute selections.
    expect(computeXPath(personType.id, indexById, parentById)).toBeNull();
  });

  it("terminates without infinite looping on cyclic parent chains", () => {
    const { indexById } = buildIndex(smallModel);
    const cyclic = new Map<string, string>();
    const firstName = Array.from(indexById.values()).find(
      (e) => e.kind === "element" && e.label === "FirstName",
    )!;
    const lastName = Array.from(indexById.values()).find(
      (e) => e.kind === "element" && e.label === "LastName",
    )!;
    cyclic.set(firstName.id, lastName.id);
    cyclic.set(lastName.id, firstName.id);
    const path = computeXPath(firstName.id, indexById, cyclic);
    // Doesn't hang, and produces a finite (possibly partial) path.
    expect(path).not.toBeNull();
    expect(path!.length).toBeLessThan(10);
  });

  it("returns null for a selectedId that is not in the index", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    expect(computeXPath("element:does-not-exist", indexById, parentById)).toBeNull();
  });

  it("returns null when a named complexType has no referencing element", () => {
    const { indexById, parentById } = buildIndex(smallModel);
    // Build a standalone index with only PersonType — no element references it.
    const stripped = new Map<string, NodeIndexEntry>();
    for (const entry of indexById.values()) {
      if (entry.kind === "complexType") stripped.set(entry.id, entry);
    }
    const personType = Array.from(stripped.values())[0]!;
    // Even if we start from a child inside PersonType (which won't exist in
    // `stripped`), walking up from a synthetic element entry that points into
    // PersonType must bail out cleanly.
    const synthetic: NodeIndexEntry = {
      id: "element:synthetic/Leaf",
      kind: "element",
      label: "Leaf",
      qname: null,
      source_ref: null,
      node: {
        id: "element:synthetic/Leaf",
        name: "Leaf",
        qname: null,
        ref: null,
        type_name: null,
        type_inline_simple: null,
        type_inline_complex: null,
        min_occurs: 1,
        max_occurs: 1,
        default: null,
        fixed: null,
        nillable: false,
        abstract: false,
        substitution_group: null,
        form: null,
        target_namespace: null,
        is_global: false,
        annotation: null,
        source_ref: null,
      },
    };
    stripped.set(synthetic.id, synthetic);
    const linkedParents = new Map(parentById);
    linkedParents.set(synthetic.id, personType.id);
    const path = computeXPath(synthetic.id, stripped, linkedParents);
    expect(path).toBeNull();
  });
});
