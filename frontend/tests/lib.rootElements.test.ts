import { describe, expect, it } from "vitest";
import { computeRootElements } from "../src/lib/rootElements";
import type {
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../src/types/schema";

const NS = "http://example.com/ns";

function globalElement(name: string, typeName: string | null): ElementDecl {
  return {
    id: `element:{${NS}}${name}`,
    name,
    qname: `{${NS}}${name}`,
    ref: null,
    type_name: typeName,
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
    target_namespace: NS,
    is_global: true,
    annotation: null,
    source_ref: { file_id: "f1", line: 1 },
  };
}

// A particle that references a global element by ``ref`` (no inline name/type).
function refParticle(ref: string): Particle {
  return {
    kind: "element",
    min_occurs: 1,
    max_occurs: 1,
    element: {
      ...globalElement("__ref__", null),
      id: `element:ref:${ref}`,
      name: null,
      qname: null,
      ref,
      is_global: false,
      target_namespace: null,
    },
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

function complexType(name: string, children: Particle[]): ComplexType {
  return {
    id: `complexType:{${NS}}${name}`,
    name,
    anonymous: false,
    abstract: false,
    mixed: false,
    content_kind: "complex",
    derivation: "none",
    base: null,
    particle: {
      kind: "sequence",
      min_occurs: 1,
      max_occurs: 1,
      element: null,
      group_ref: null,
      group_inline: null,
      children,
      wildcard_namespace: null,
      wildcard_process_contents: null,
      annotation: null,
    },
    attributes: [],
    attribute_group_refs: [],
    simple_content_base: null,
    simple_content_facets: [],
    annotation: null,
    source_ref: { file_id: "f1", line: 1 },
  };
}

function model(
  elements: ElementDecl[],
  complexTypes: ComplexType[],
): SchemaModel {
  return {
    schema_id: "test",
    target_namespace: NS,
    namespaces: { tns: NS, xs: "http://www.w3.org/2001/XMLSchema" },
    element_form_default: "qualified",
    attribute_form_default: "unqualified",
    elements,
    attributes: [],
    simple_types: [],
    complex_types: complexTypes,
    groups: [],
    attribute_groups: [],
    files: [
      {
        id: "f1",
        filename: "main.xsd",
        target_namespace: NS,
        relationship: "main",
        content: null,
      },
    ],
    diagnostics: [],
  };
}

describe("computeRootElements", () => {
  it("drops globals that are referenced via ref= elsewhere", () => {
    // Root (unreferenced) + Child (referenced inside RootType) + Orphan
    // (unreferenced global, e.g. from an included file).
    const root = globalElement("Root", "tns:RootType");
    const child = globalElement("Child", "xs:string");
    const orphan = globalElement("Orphan", "xs:string");
    const rootType = complexType("RootType", [refParticle("tns:Child")]);

    const roots = computeRootElements(model([root, child, orphan], [rootType]));

    expect(roots.map((e) => e.name)).toEqual(["Root", "Orphan"]);
  });

  it("returns every element unchanged when there are no refs", () => {
    const a = globalElement("A", "xs:string");
    const b = globalElement("B", "xs:string");

    const roots = computeRootElements(model([a, b], []));

    expect(roots.map((e) => e.name)).toEqual(["A", "B"]);
  });

  it("falls back to the full list when every global is referenced", () => {
    // A recursive root references itself — filtering would leave nothing, so
    // the safeguard keeps the view non-empty.
    const a = globalElement("A", "tns:AType");
    const aType = complexType("AType", [refParticle("tns:A")]);

    const roots = computeRootElements(model([a], [aType]));

    expect(roots.map((e) => e.name)).toEqual(["A"]);
  });

  it("matches refs that resolve by bare local name", () => {
    const root = globalElement("Root", "tns:RootType");
    const child = globalElement("Child", "xs:string");
    // ref written without a prefix should still resolve to the global.
    const rootType = complexType("RootType", [refParticle("Child")]);

    const roots = computeRootElements(model([root, child], [rootType]));

    expect(roots.map((e) => e.name)).toEqual(["Root"]);
  });
});
