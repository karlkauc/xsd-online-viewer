import { describe, expect, it } from "vitest";
import { buildTreeRows } from "../src/components/TreeView/treeRows";
import { buildIndex } from "../src/lib/indexSchema";
import { smallModel } from "./fixtures/smallModel";
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
