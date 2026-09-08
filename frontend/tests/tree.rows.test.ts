import { describe, expect, it } from "vitest";
import { buildTreeRows } from "../src/components/TreeView/treeRows";
import { buildIndex } from "../src/lib/indexSchema";
import { smallModel } from "./fixtures/smallModel";
import { refModel, DOCUMENT_ID, SIGNATURE_REF_ID } from "./fixtures/refModel";
import { constraintsModel, libraryElement } from "./fixtures/constraintsModel";
import type { SchemaNodeKind } from "../src/types/schema";

const ALL: SchemaNodeKind[] = [
  "element",
  "attribute",
  "complexType",
  "simpleType",
  "group",
  "attributeGroup",
];

describe("buildTreeRows", () => {
  it("shows top-level globals when nothing is expanded", () => {
    const { indexById } = buildIndex(smallModel);
    const rows = buildTreeRows(smallModel, new Set(), new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    expect(labels).toContain("Person");
    expect(labels).toContain("PersonType");
    expect(labels).toContain("AgeType");
  });

  it("drills into a Person's PersonType when expanded", () => {
    const { indexById } = buildIndex(smallModel);
    const expanded = new Set(["element:{http://example.com/simple}Person"]);
    const rows = buildTreeRows(smallModel, expanded, new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    expect(labels).toContain("FirstName");
    expect(labels).toContain("@id");
  });

  it("respects the type-kind filter", () => {
    const { indexById } = buildIndex(smallModel);
    const rows = buildTreeRows(smallModel, new Set(), new Set(["simpleType"]), indexById);
    expect(rows.every((r) => r.kind === "simpleType")).toBe(true);
  });
});

describe("buildTreeRows element references", () => {
  it("follows an imported ref to the global declaration when expanded", () => {
    const { indexById } = buildIndex(refModel);
    const collapsed = buildTreeRows(refModel, new Set([DOCUMENT_ID]), new Set(ALL), indexById);
    const signature = collapsed.find((r) => r.label === "ds:Signature");
    expect(signature).toBeDefined();
    // The referenced global carries the type, so the row is drillable.
    expect(signature!.hasChildren).toBe(true);
    expect(signature!.typeHint).toBe("ds:SignatureType");

    const expanded = buildTreeRows(
      refModel,
      new Set([DOCUMENT_ID, SIGNATURE_REF_ID]),
      new Set(ALL),
      indexById,
    );
    const labels = expanded.map((r) => r.label);
    expect(labels).toContain("ds:SignedInfo");
    expect(labels).toContain("@Id");
  });
});

describe("buildTreeRows identity constraints", () => {
  it("carries the constraint count and title on the declaring element's row", () => {
    const { indexById } = buildIndex(constraintsModel);
    const rows = buildTreeRows(constraintsModel, new Set(), new Set(ALL), indexById);
    const library = rows.find((r) => r.id === libraryElement.id);
    expect(library).toBeDefined();
    expect(library!.constraintCount).toBe(4);
    expect(library!.constraintTitle).toBe(
      "key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef",
    );
  });

  it("leaves constraintCount unset for elements without identity constraints", () => {
    const { indexById } = buildIndex(constraintsModel);
    const expanded = new Set([libraryElement.id]);
    const rows = buildTreeRows(constraintsModel, expanded, new Set(ALL), indexById);
    const books = rows.find((r) => r.label === "Books");
    expect(books).toBeDefined();
    expect(books!.constraintCount ?? 0).toBe(0);
  });
});
