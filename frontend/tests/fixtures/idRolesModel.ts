import type { AttributeDecl, ElementDecl, Particle, SchemaModel } from "../../src/types/schema";

// Small model exercising ElementDecl.id_role / AttributeDecl.id_role.
// Mirrors the shape backend/app/parser/idroles.py classifies: one xs:ID
// declaration, one xs:IDREF, one xs:IDREFS, plus one plain element/attribute
// carrying no role at all (id_role omitted, as the backend leaves it).

const NS = "http://example.com/idroles";

function elementParticle(element: ElementDecl): Particle {
  return {
    kind: "element",
    min_occurs: element.min_occurs,
    max_occurs: element.max_occurs,
    element,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

export const uniqueIdElement: ElementDecl = {
  id: `element:{${NS}}UniqueID`,
  name: "UniqueID",
  qname: `{${NS}}UniqueID`,
  ref: null,
  type_name: "xs:ID",
  type_inline_simple: null,
  type_inline_complex: null,
  min_occurs: 1,
  max_occurs: 1,
  default: null,
  fixed: null,
  nillable: false,
  abstract: false,
  substitution_group: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 5 },
  id_role: "id",
};

export const benchmarkRefElement: ElementDecl = {
  id: `element:{${NS}}BenchmarkRef`,
  name: "BenchmarkRef",
  qname: `{${NS}}BenchmarkRef`,
  ref: null,
  type_name: "xs:IDREF",
  type_inline_simple: null,
  type_inline_complex: null,
  min_occurs: 1,
  max_occurs: 1,
  default: null,
  fixed: null,
  nillable: false,
  abstract: false,
  substitution_group: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 6 },
  id_role: "idref",
};

export const relatedRefsElement: ElementDecl = {
  id: `element:{${NS}}RelatedRefs`,
  name: "RelatedRefs",
  qname: `{${NS}}RelatedRefs`,
  ref: null,
  type_name: "xs:IDREFS",
  type_inline_simple: null,
  type_inline_complex: null,
  min_occurs: 1,
  max_occurs: 1,
  default: null,
  fixed: null,
  nillable: false,
  abstract: false,
  substitution_group: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 7 },
  id_role: "idrefs",
};

export const plainElement: ElementDecl = {
  id: `element:{${NS}}Plain`,
  name: "Plain",
  qname: `{${NS}}Plain`,
  ref: null,
  type_name: "xs:string",
  type_inline_simple: null,
  type_inline_complex: null,
  min_occurs: 1,
  max_occurs: 1,
  default: null,
  fixed: null,
  nillable: false,
  abstract: false,
  substitution_group: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 8 },
};

export const refAttribute: AttributeDecl = {
  id: `attribute:{${NS}}refAttr`,
  name: "refAttr",
  qname: `{${NS}}refAttr`,
  ref: null,
  type_name: "xs:IDREF",
  type_inline: null,
  use: "optional",
  default: null,
  fixed: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 9 },
  id_role: "idref",
};

export const plainAttribute: AttributeDecl = {
  id: `attribute:{${NS}}plainAttr`,
  name: "plainAttr",
  qname: `{${NS}}plainAttr`,
  ref: null,
  type_name: "xs:string",
  type_inline: null,
  use: "optional",
  default: null,
  fixed: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 10 },
};

// A holder element wraps everything into a content model so buildIndex's
// visitElement/visitParticle/visitAttribute walk them all.
const holderParticle: Particle = {
  kind: "sequence",
  min_occurs: 1,
  max_occurs: 1,
  element: null,
  group_ref: null,
  group_inline: null,
  children: [
    elementParticle(uniqueIdElement),
    elementParticle(benchmarkRefElement),
    elementParticle(relatedRefsElement),
    elementParticle(plainElement),
  ],
  wildcard_namespace: null,
  wildcard_process_contents: null,
  annotation: null,
};

export const holderElement: ElementDecl = {
  id: `element:{${NS}}Holder`,
  name: "Holder",
  qname: `{${NS}}Holder`,
  ref: null,
  type_name: null,
  type_inline_simple: null,
  type_inline_complex: {
    id: `complexType:{${NS}}Holder/anon`,
    name: null,
    anonymous: true,
    abstract: false,
    mixed: false,
    content_kind: "complex",
    derivation: "none",
    base: null,
    particle: holderParticle,
    attributes: [refAttribute, plainAttribute],
    attribute_group_refs: [],
    simple_content_base: null,
    simple_content_facets: [],
    annotation: null,
    source_ref: { file_id: "f1", line: 4 },
  },
  min_occurs: 1,
  max_occurs: 1,
  default: null,
  fixed: null,
  nillable: false,
  abstract: false,
  substitution_group: null,
  form: "qualified",
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 3 },
};

export const idRolesModel: SchemaModel = {
  schema_id: "test-id-roles",
  target_namespace: NS,
  namespaces: { xs: "http://www.w3.org/2001/XMLSchema", tns: NS },
  element_form_default: "qualified",
  attribute_form_default: "qualified",
  elements: [holderElement],
  attributes: [],
  simple_types: [],
  complex_types: [],
  groups: [],
  attribute_groups: [],
  files: [
    {
      id: "f1",
      filename: "id_roles.xsd",
      target_namespace: NS,
      relationship: "main",
      content: "<xs:schema/>",
    },
  ],
  diagnostics: [],
};
