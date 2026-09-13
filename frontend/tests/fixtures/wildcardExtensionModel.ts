import type {
  Annotation,
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../../src/types/schema";

// Mirrors the shape of GLEIF's LEI-CDF 3.1 `LEIHeader`: a sequence whose last
// member (`Extension`) is documented, optional, and expands into a type that
// holds nothing but an `<xs:any>` wildcard. The expanded subtree is therefore
// much shorter than the element node itself — the case that used to make the
// element protrude above the band its parent allotted it.

export const NS = "http://example.com/wildcard";

function doc(text: string): Annotation {
  return {
    documentation: [{ lang: "en", text, source: "documentation" }],
    appinfo: [],
    comments: [],
  };
}

function child(
  name: string,
  typeName: string | null,
  annotation: Annotation | null,
): ElementDecl {
  return {
    id: `element:{${NS}}LEIHeaderType/${name}`,
    name,
    qname: null,
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
    target_namespace: null,
    is_global: false,
    annotation,
    source_ref: { file_id: "f1", line: 1 },
  };
}

function elementParticle(element: ElementDecl, minOccurs = 1): Particle {
  return {
    kind: "element",
    min_occurs: minOccurs,
    max_occurs: 1,
    element,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

const anyParticle: Particle = {
  kind: "any",
  min_occurs: 0,
  max_occurs: "unbounded",
  element: null,
  group_ref: null,
  group_inline: null,
  children: [],
  wildcard_namespace: "##other",
  wildcard_process_contents: "lax",
  annotation: null,
};

function wildcardOnlyType(name: string): ComplexType {
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
      children: [anyParticle],
      wildcard_namespace: null,
      wildcard_process_contents: null,
      annotation: null,
    },
    attributes: [],
    attribute_group_refs: [],
    simple_content_base: null,
    simple_content_facets: [],
    annotation: null,
    source_ref: { file_id: "f1", line: 2 },
  };
}

export const HEADER_ID = `element:{${NS}}LEIHeader`;
export const NEXT_VERSION_ID = `element:{${NS}}LEIHeaderType/NextVersion`;
export const EXTENSION_ID = `element:{${NS}}LEIHeaderType/Extension`;

const recordCount = child(
  "RecordCount",
  "xs:nonNegativeInteger",
  doc("The number of LEI data records in this file."),
);
const nextVersion = child(
  "NextVersion",
  "tns:HeaderNextVersionType",
  doc(
    "A structure for adding further elements in to the LEI data file header\nin anticipation of a new version.",
  ),
);
const extension = child(
  "Extension",
  "tns:ExtensionType",
  doc(
    "This lei:Extension element may contain any additional elements required\nto extend the LEIHeader.",
  ),
);

export const wildcardExtensionModel: SchemaModel = {
  schema_id: "test",
  target_namespace: NS,
  namespaces: { xs: "http://www.w3.org/2001/XMLSchema", tns: NS },
  element_form_default: "qualified",
  attribute_form_default: "unqualified",
  elements: [
    {
      ...child("LEIHeader", "tns:LEIHeaderType", null),
      id: HEADER_ID,
      qname: `{${NS}}LEIHeader`,
      target_namespace: NS,
      is_global: true,
    },
  ],
  attributes: [],
  simple_types: [],
  complex_types: [
    {
      id: `complexType:{${NS}}LEIHeaderType`,
      name: "LEIHeaderType",
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
        children: [
          elementParticle(recordCount),
          elementParticle(nextVersion, 0),
          elementParticle(extension, 0),
        ],
        wildcard_namespace: null,
        wildcard_process_contents: null,
        annotation: null,
      },
      attributes: [],
      attribute_group_refs: [],
      simple_content_base: null,
      simple_content_facets: [],
      annotation: null,
      source_ref: { file_id: "f1", line: 3 },
    },
    wildcardOnlyType("HeaderNextVersionType"),
    wildcardOnlyType("ExtensionType"),
  ],
  groups: [],
  attribute_groups: [],
  diagnostics: [],
  files: [
    {
      id: "f1",
      filename: "lei.xsd",
      target_namespace: NS,
      relationship: "main",
      content: null,
    },
  ],
};
