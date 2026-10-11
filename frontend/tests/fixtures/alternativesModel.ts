// An element whose type depends on an attribute (XSD 1.1 xs:alternative), and
// a type with open content.

import type { ComplexType, ElementDecl, Particle, SchemaModel } from "../../src/types/schema";
import { smallModel } from "./smallModel";

function particle(kind: Particle["kind"], overrides: Partial<Particle> = {}): Particle {
  return {
    kind,
    min_occurs: 1,
    max_occurs: 1,
    element: null,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
    ...overrides,
  };
}

function leaf(name: string): ElementDecl {
  return {
    id: `element:Shape/${name}`,
    name,
    qname: null,
    ref: null,
    type_name: "xs:int",
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
  };
}

function type(name: string, children: string[], extra: Partial<ComplexType> = {}): ComplexType {
  return {
    id: `complexType:${name}`,
    name,
    anonymous: false,
    abstract: false,
    mixed: false,
    content_kind: "complex",
    derivation: "none",
    base: null,
    particle: particle("sequence", {
      children: children.map((child) => particle("element", { element: leaf(child) })),
    }),
    attributes: [],
    attribute_group_refs: [],
    simple_content_base: null,
    simple_content_facets: [],
    annotation: null,
    source_ref: null,
    ...extra,
  };
}

export const SHAPE_ID = "element:Shape";

export const shapeElement: ElementDecl = {
  ...leaf("Shape"),
  id: SHAPE_ID,
  qname: "Shape",
  type_name: "Base",
  is_global: true,
  alternatives: [
    {
      test: "@kind = 'circle'",
      type_name: "Circle",
      type_inline_simple: null,
      type_inline_complex: null,
      xpath_default_namespace: null,
      annotation: null,
      source_ref: null,
    },
    {
      test: "@kind = 'square'",
      type_name: "Square",
      type_inline_simple: null,
      type_inline_complex: null,
      xpath_default_namespace: null,
      annotation: null,
      source_ref: null,
    },
  ],
};

export const alternativesModel: SchemaModel = {
  ...smallModel,
  xsd_version: "1.1",
  elements: [shapeElement],
  attributes: [],
  simple_types: [],
  groups: [],
  attribute_groups: [],
  complex_types: [
    type("Base", ["id"]),
    type("Circle", ["radius"], {
      open_content: {
        mode: "suffix",
        origin: "own",
        applies_to_empty: false,
        wildcard: {
          namespace: "##other",
          not_namespace: null,
          not_qname: null,
          process_contents: "lax",
          annotation: null,
        },
        annotation: null,
        source_ref: null,
      },
    }),
    type("Square", ["side"]),
  ],
};
