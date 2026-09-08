import type {
  Assertion,
  AttributeDecl,
  ComplexType,
  ElementDecl,
  SchemaModel,
  SimpleType,
} from "../../src/types/schema";

// Model exercising every assertion-collection path in lib/assertions.ts:
//  - a named complex type with 2 asserts (mirrors samples/xsd-1.1/measurement.xsd)
//  - a named simple type with an xs:assertion, used by an element AND an attribute
//  - an inline simple type with its own assertion
//  - an extension chain where both the base and derived complex type assert
//  - a complexType with simpleContent whose base simple type asserts
//  - a self-referential extension complex type (cycle guard)

const NS = "http://example.com/assert";

function assertion(test: string, line: number): Assertion {
  return {
    test,
    xpath_default_namespace: null,
    annotation: null,
    source_ref: { file_id: "f1", line },
  };
}

// --- Named complex type with 2 asserts ------------------------------------

export const measurementType: ComplexType = {
  id: `complexType:{${NS}}MeasurementType`,
  name: "MeasurementType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 30 },
  assertions: [
    assertion("xs:date(@from) le xs:date(@to)", 38),
    assertion("count(Value) gt 0", 41),
  ],
};

export const measurementElement: ElementDecl = {
  id: `element:{${NS}}Measurement`,
  name: "Measurement",
  qname: `{${NS}}Measurement`,
  ref: null,
  type_name: "tns:MeasurementType",
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
  source_ref: { file_id: "f1", line: 29 },
};

// --- Named simple type with an assertion, used by an element AND an attribute ---

export const positiveCodeType: SimpleType = {
  id: `simpleType:{${NS}}PositiveCode`,
  name: "PositiveCode",
  anonymous: false,
  derivation: "restriction",
  base: "xs:string",
  item_type: null,
  item_inline: null,
  member_types: [],
  member_inline: [],
  facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 50 },
  assertions: [assertion("string-length($value) gt 0", 52)],
};

export const codeElement: ElementDecl = {
  id: `element:{${NS}}Code`,
  name: "Code",
  qname: `{${NS}}Code`,
  ref: null,
  type_name: "tns:PositiveCode",
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
  source_ref: { file_id: "f1", line: 55 },
};

export const codeAttribute: AttributeDecl = {
  id: `attribute:{${NS}}code`,
  name: "code",
  qname: `{${NS}}code`,
  ref: null,
  type_name: "tns:PositiveCode",
  type_inline: null,
  use: "optional",
  default: null,
  fixed: null,
  form: null,
  target_namespace: NS,
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 56 },
};

// --- Inline simple type with its own assertion -----------------------------

export const inlineCodedType: SimpleType = {
  id: `simpleType:{${NS}}InlineCoded/anon`,
  name: null,
  anonymous: true,
  derivation: "restriction",
  base: "xs:string",
  item_type: null,
  item_inline: null,
  member_types: [],
  member_inline: [],
  facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 60 },
  assertions: [assertion("matches($value, '^[A-Z]+$')", 61)],
};

export const inlineCodedElement: ElementDecl = {
  id: `element:{${NS}}InlineCoded`,
  name: "InlineCoded",
  qname: `{${NS}}InlineCoded`,
  ref: null,
  type_name: null,
  type_inline_simple: inlineCodedType,
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
  source_ref: { file_id: "f1", line: 59 },
};

// --- Extension chain: base and derived complex types both assert ----------

export const baseAssertType: ComplexType = {
  id: `complexType:{${NS}}BaseAssertType`,
  name: "BaseAssertType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 70 },
  assertions: [assertion("@base-flag = 'ok'", 71)],
};

export const derivedAssertType: ComplexType = {
  id: `complexType:{${NS}}DerivedAssertType`,
  name: "DerivedAssertType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "extension",
  base: "tns:BaseAssertType",
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 75 },
  assertions: [assertion("@derived-flag = 'ok'", 76)],
};

export const derivedElement: ElementDecl = {
  id: `element:{${NS}}Derived`,
  name: "Derived",
  qname: `{${NS}}Derived`,
  ref: null,
  type_name: "tns:DerivedAssertType",
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
  source_ref: { file_id: "f1", line: 74 },
};

// --- Restriction chain: base and derived (via restriction) complex types
// both assert. XSD 1.1 inherits a complex type's assertions through
// complexContent/simpleContent *restriction* just like extension. -----------

export const restrictedAssertType: ComplexType = {
  id: `complexType:{${NS}}RestrictedAssertType`,
  name: "RestrictedAssertType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "restriction",
  base: "tns:BaseAssertType",
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 95 },
  assertions: [assertion("@restricted-flag = 'ok'", 96)],
};

export const restrictedElement: ElementDecl = {
  id: `element:{${NS}}Restricted`,
  name: "Restricted",
  qname: `{${NS}}Restricted`,
  ref: null,
  type_name: "tns:RestrictedAssertType",
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
  source_ref: { file_id: "f1", line: 94 },
};

// --- complexType with simpleContent whose base simple type asserts --------

export const amountValueType: SimpleType = {
  id: `simpleType:{${NS}}AmountValue`,
  name: "AmountValue",
  anonymous: false,
  derivation: "restriction",
  base: "xs:decimal",
  item_type: null,
  item_inline: null,
  member_types: [],
  member_inline: [],
  facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 80 },
  assertions: [assertion("$value ge 0", 81)],
};

export const amountType: ComplexType = {
  id: `complexType:{${NS}}AmountType`,
  name: "AmountType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "simple",
  derivation: "extension",
  base: "tns:AmountValue",
  particle: null,
  attributes: [
    {
      id: `attribute:{${NS}}AmountType/@ccy`,
      name: "ccy",
      qname: null,
      ref: null,
      type_name: "xs:string",
      type_inline: null,
      use: "required",
      default: null,
      fixed: null,
      form: null,
      target_namespace: null,
      is_global: false,
      annotation: null,
      source_ref: { file_id: "f1", line: 85 },
    },
  ],
  attribute_group_refs: [],
  simple_content_base: "tns:AmountValue",
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 84 },
};

export const paymentElement: ElementDecl = {
  id: `element:{${NS}}Payment`,
  name: "Payment",
  qname: `{${NS}}Payment`,
  ref: null,
  type_name: "tns:AmountType",
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
  source_ref: { file_id: "f1", line: 83 },
};

// --- Self-referential extension (cycle guard) -------------------------------

export const cyclicType: ComplexType = {
  id: `complexType:{${NS}}CyclicType`,
  name: "CyclicType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "extension",
  base: "tns:CyclicType",
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 90 },
  assertions: [assertion("@x = 'y'", 91)],
};

export const cyclicElement: ElementDecl = {
  id: `element:{${NS}}Cyclic`,
  name: "Cyclic",
  qname: `{${NS}}Cyclic`,
  ref: null,
  type_name: "tns:CyclicType",
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
  source_ref: { file_id: "f1", line: 89 },
};

export const assertionsModel: SchemaModel = {
  schema_id: "test-assertions",
  target_namespace: NS,
  namespaces: { xs: "http://www.w3.org/2001/XMLSchema", tns: NS },
  element_form_default: "qualified",
  attribute_form_default: "unqualified",
  elements: [
    measurementElement,
    codeElement,
    inlineCodedElement,
    derivedElement,
    restrictedElement,
    paymentElement,
    cyclicElement,
  ],
  attributes: [codeAttribute],
  simple_types: [positiveCodeType, amountValueType],
  complex_types: [
    measurementType,
    baseAssertType,
    derivedAssertType,
    restrictedAssertType,
    amountType,
    cyclicType,
  ],
  groups: [],
  attribute_groups: [],
  files: [
    {
      id: "f1",
      filename: "assertions.xsd",
      target_namespace: NS,
      relationship: "main",
      content: null,
    },
  ],
  diagnostics: [],
  xsd_version: "1.1",
};
