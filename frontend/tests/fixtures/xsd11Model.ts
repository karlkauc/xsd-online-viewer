import type {
  ElementDecl,
  SchemaModel,
  SimpleType,
  VersionConstraints,
} from "../../src/types/schema";

// Minimal XSD 1.1 model used by Phase-1 tests. Grows as later phases add
// assertions, alternatives, openContent, etc.

const minVersion11: VersionConstraints = {
  min_version: "1.1",
  max_version: null,
  type_available: null,
  type_unavailable: null,
  facet_available: null,
  facet_unavailable: null,
};

const needsDateTimeStamp: VersionConstraints = {
  min_version: null,
  max_version: null,
  type_available: "xs:dateTimeStamp",
  type_unavailable: null,
  facet_available: null,
  facet_unavailable: null,
};

const eventElement: ElementDecl = {
  id: "element:{http://example.com/vc}Event",
  name: "Event",
  qname: "{http://example.com/vc}Event",
  ref: null,
  type_name: "tns:EventType",
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
  target_namespace: "http://example.com/vc",
  is_global: true,
  annotation: null,
  source_ref: { file_id: "f1", line: 14 },
  version_constraints: needsDateTimeStamp,
};

const legacyToken: SimpleType = {
  id: "simpleType:{http://example.com/vc}LegacyToken",
  name: "LegacyToken",
  anonymous: false,
  derivation: "restriction",
  base: "xs:string",
  item_type: null,
  item_inline: null,
  member_types: [],
  member_inline: [],
  facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 24 },
  version_constraints: minVersion11,
};

export const xsd11Model: SchemaModel = {
  schema_id: "test-vc",
  target_namespace: "http://example.com/vc",
  namespaces: {
    xs: "http://www.w3.org/2001/XMLSchema",
    vc: "http://www.w3.org/2007/XMLSchema-versioning",
    tns: "http://example.com/vc",
  },
  element_form_default: "qualified",
  attribute_form_default: "unqualified",
  elements: [eventElement],
  attributes: [],
  simple_types: [legacyToken],
  complex_types: [],
  groups: [],
  attribute_groups: [],
  files: [
    {
      id: "f1",
      filename: "vc-versioning.xsd",
      target_namespace: "http://example.com/vc",
      relationship: "main",
      content: "<xs:schema/>",
    },
  ],
  diagnostics: [],
  xsd_version: "1.1",
  xpath_default_namespace: "http://example.com/vc",
  default_attributes: "tns:CommonAttrs",
  default_open_content: null,
};
