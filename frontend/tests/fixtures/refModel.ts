import type {
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../../src/types/schema";

// Mirrors the shape the backend produces for a schema that imports another
// namespace and references one of its globals — the FundsXML4 / xmldsig case:
//
//   <xs:import namespace="…xmldsig#" schemaLocation="xmldsig-core-schema.xsd"/>
//   <xs:element ref="ds:Signature" minOccurs="0"/>
//
// The referenced declarations live in the imported file, so they are not
// document roots; the views must reach them through ``ref_id``.

const DS = "http://www.w3.org/2000/09/xmldsig#";

export const SIGNATURE_ID = `element:{${DS}}Signature`;
export const SIGNED_INFO_ID = `element:{${DS}}SignedInfo`;
export const DOCUMENT_ID = "element:{http://example.com/host}Document";
export const SIGNATURE_REF_ID = "element:ds:Signature";

function element(over: Partial<ElementDecl> & { id: string }): ElementDecl {
  return {
    name: null,
    qname: null,
    ref: null,
    ref_id: null,
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
    source_ref: { file_id: "f1", line: 1 },
    ...over,
  };
}

function particle(el: ElementDecl, minOccurs = 1): Particle {
  return {
    kind: "element",
    min_occurs: minOccurs,
    max_occurs: 1,
    element: el,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

function sequence(children: Particle[]): Particle {
  return {
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
  };
}

const documentInlineType: ComplexType = {
  id: "complexType:anon-1",
  name: null,
  anonymous: true,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([
    particle(
      element({
        id: "element:anon-2",
        name: "Body",
        type_name: "xs:string",
        source_ref: { file_id: "f1", line: 9 },
      }),
    ),
    particle(
      element({
        id: SIGNATURE_REF_ID,
        ref: "ds:Signature",
        ref_id: SIGNATURE_ID,
        min_occurs: 0,
        source_ref: { file_id: "f1", line: 10 },
      }),
      0,
    ),
  ]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 7 },
};

const signatureType: ComplexType = {
  id: `complexType:{${DS}}SignatureType`,
  name: "SignatureType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([
    particle(
      element({
        id: "element:ds:SignedInfo",
        ref: "ds:SignedInfo",
        ref_id: SIGNED_INFO_ID,
        source_ref: { file_id: "f2", line: 12 },
      }),
    ),
  ]),
  attributes: [
    {
      id: `attribute:{${DS}}SignatureType/@Id`,
      name: "Id",
      qname: null,
      ref: null,
      type_name: "xs:ID",
      type_inline: null,
      use: "optional",
      default: null,
      fixed: null,
      form: null,
      target_namespace: null,
      is_global: false,
      annotation: null,
      source_ref: { file_id: "f2", line: 14 },
    },
  ],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f2", line: 11 },
};

export const refModel: SchemaModel = {
  schema_id: "test-ref",
  target_namespace: "http://example.com/host",
  namespaces: { xs: "http://www.w3.org/2001/XMLSchema", ds: DS },
  element_form_default: "qualified",
  attribute_form_default: "unqualified",
  elements: [
    element({
      id: DOCUMENT_ID,
      name: "Document",
      qname: "{http://example.com/host}Document",
      target_namespace: "http://example.com/host",
      is_global: true,
      type_inline_complex: documentInlineType,
      source_ref: { file_id: "f1", line: 6 },
    }),
    element({
      id: SIGNATURE_ID,
      name: "Signature",
      qname: `{${DS}}Signature`,
      type_name: "ds:SignatureType",
      target_namespace: DS,
      is_global: true,
      source_ref: { file_id: "f2", line: 10 },
    }),
    element({
      id: SIGNED_INFO_ID,
      name: "SignedInfo",
      qname: `{${DS}}SignedInfo`,
      type_name: "xs:string",
      target_namespace: DS,
      is_global: true,
      source_ref: { file_id: "f2", line: 20 },
    }),
  ],
  attributes: [],
  simple_types: [],
  complex_types: [signatureType],
  groups: [],
  attribute_groups: [],
  files: [
    {
      id: "f1",
      filename: "host.xsd",
      target_namespace: "http://example.com/host",
      relationship: "main",
      content: "<xs:schema/>",
    },
    {
      id: "f2",
      filename: "xmldsig-core-schema.xsd",
      target_namespace: DS,
      relationship: "import",
      content: "<xs:schema/>",
    },
  ],
  diagnostics: [],
};
