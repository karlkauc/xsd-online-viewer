import type {
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../../src/types/schema";

// A tiny in-memory model used by unit tests. Mirrors the output the backend
// would produce for a PersonType-style schema.

function leafElement(name: string, typeName: string, line: number): ElementDecl {
  return {
    id: `element:{http://example.com/simple}PersonType/${name}`,
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
    annotation: null,
    source_ref: { file_id: "f1", line },
  };
}

function elementParticle(element: ElementDecl): Particle {
  return {
    kind: "element",
    min_occurs: 1,
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

const addressInlineType: ComplexType = {
  id: "complexType:{http://example.com/simple}PersonType/Address/anon",
  name: null,
  anonymous: true,
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
      elementParticle(leafElement("Street", "xs:string", 11)),
      elementParticle(leafElement("City", "xs:string", 12)),
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
  source_ref: { file_id: "f1", line: 10 },
};

const addressElement: ElementDecl = {
  ...leafElement("Address", "", 9),
  type_name: null,
  type_inline_complex: addressInlineType,
};

const ageElement: ElementDecl = {
  ...leafElement("Age", "tns:AgeType", 14),
};

const colorElement: ElementDecl = {
  ...leafElement("Color", "tns:ColorType", 16),
};

export const smallModel: SchemaModel = {
  schema_id: "test",
  target_namespace: "http://example.com/simple",
  namespaces: { xs: "http://www.w3.org/2001/XMLSchema", tns: "http://example.com/simple" },
  element_form_default: "qualified",
  attribute_form_default: "unqualified",
  elements: [
    {
      id: "element:{http://example.com/simple}Person",
      name: "Person",
      qname: "{http://example.com/simple}Person",
      ref: null,
      type_name: "tns:PersonType",
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
      target_namespace: "http://example.com/simple",
      is_global: true,
      annotation: {
        documentation: [
          { lang: "en", text: "Represents a person.", source: "documentation" },
        ],
        appinfo: [],
        comments: [],
      },
      source_ref: { file_id: "f1", line: 5 },
    },
  ],
  attributes: [],
  simple_types: [
    {
      id: "simpleType:{http://example.com/simple}AgeType",
      name: "AgeType",
      anonymous: false,
      derivation: "restriction",
      base: "xs:int",
      item_type: null,
      item_inline: null,
      member_types: [],
      member_inline: [],
      facets: [
        { kind: "minInclusive", value: "0", fixed: false, annotation: null },
        { kind: "maxInclusive", value: "130", fixed: false, annotation: null },
      ],
      annotation: null,
      source_ref: { file_id: "f1", line: 15 },
    },
    {
      id: "simpleType:{http://example.com/simple}ColorType",
      name: "ColorType",
      anonymous: false,
      derivation: "restriction",
      base: "xs:string",
      item_type: null,
      item_inline: null,
      member_types: [],
      member_inline: [],
      facets: [
        { kind: "enumeration", value: "red", fixed: false, annotation: null },
        { kind: "enumeration", value: "green", fixed: false, annotation: null },
        { kind: "enumeration", value: "blue", fixed: false, annotation: null },
      ],
      annotation: null,
      source_ref: { file_id: "f1", line: 20 },
    },
  ],
  complex_types: [
    {
      id: "complexType:{http://example.com/simple}PersonType",
      name: "PersonType",
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
          elementParticle(leafElement("FirstName", "xs:string", 7)),
          elementParticle(leafElement("LastName", "xs:string", 8)),
          elementParticle(addressElement),
          elementParticle(ageElement),
          elementParticle(colorElement),
          elementParticle(leafElement("Email", "xs:string", 13)),
        ],
        wildcard_namespace: null,
        wildcard_process_contents: null,
        annotation: null,
      },
      attributes: [
        {
          id: "attribute:{http://example.com/simple}PersonType/@id",
          name: "id",
          qname: null,
          ref: null,
          type_name: "xs:ID",
          type_inline: null,
          use: "required",
          default: null,
          fixed: null,
          form: null,
          target_namespace: null,
          is_global: false,
          annotation: null,
          source_ref: { file_id: "f1", line: 12 },
        },
      ],
      attribute_group_refs: [],
      simple_content_base: null,
      simple_content_facets: [],
      annotation: null,
      source_ref: { file_id: "f1", line: 6 },
    },
  ],
  groups: [],
  attribute_groups: [],
  files: [
    {
      id: "f1",
      filename: "simple.xsd",
      target_namespace: "http://example.com/simple",
      relationship: "main",
      content: "<xs:schema/>",
    },
  ],
  diagnostics: [],
};
