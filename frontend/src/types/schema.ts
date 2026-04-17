// Mirrors backend/app/parser/model.py. Kept in sync manually; field names
// match the snake_case emitted by pydantic's default alias generation.

export type QName = string;

export interface SourceRef {
  file_id: string;
  line: number | null;
}

export interface DocumentationFragment {
  lang: string | null;
  text: string;
  source: "documentation" | "comment";
}

export interface AppInfo {
  source_uri: string | null;
  raw_xml: string;
}

export interface Annotation {
  documentation: DocumentationFragment[];
  appinfo: AppInfo[];
  comments: string[];
}

export interface Diagnostic {
  severity: "warning" | "error";
  message: string;
  file_id: string | null;
  line: number | null;
}

export type FacetKind =
  | "enumeration"
  | "pattern"
  | "length"
  | "minLength"
  | "maxLength"
  | "minInclusive"
  | "maxInclusive"
  | "minExclusive"
  | "maxExclusive"
  | "totalDigits"
  | "fractionDigits"
  | "whiteSpace"
  | "assertion"
  | "explicitTimezone";

export interface Facet {
  kind: FacetKind;
  value: string;
  fixed: boolean;
  annotation: Annotation | null;
}

export type SimpleTypeDerivation = "restriction" | "list" | "union" | "atomic";

export interface SimpleType {
  id: string;
  name: string | null;
  anonymous: boolean;
  derivation: SimpleTypeDerivation;
  base: QName | null;
  item_type: QName | null;
  item_inline: SimpleType | null;
  member_types: QName[];
  member_inline: SimpleType[];
  facets: Facet[];
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export type AttributeUse = "required" | "optional" | "prohibited";

export interface AttributeDecl {
  id: string;
  name: string | null;
  qname: QName | null;
  ref: QName | null;
  type_name: QName | null;
  type_inline: SimpleType | null;
  use: AttributeUse;
  default: string | null;
  fixed: string | null;
  form: "qualified" | "unqualified" | null;
  target_namespace: string | null;
  is_global: boolean;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export interface AttributeGroup {
  id: string;
  name: string | null;
  ref: QName | null;
  attributes: AttributeDecl[];
  attribute_group_refs: QName[];
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export type ParticleKind =
  | "element"
  | "group-ref"
  | "sequence"
  | "choice"
  | "all"
  | "any";

export interface Particle {
  kind: ParticleKind;
  min_occurs: number;
  max_occurs: number | "unbounded";
  element: ElementDecl | null;
  group_ref: QName | null;
  group_inline: Group | null;
  children: Particle[];
  wildcard_namespace: string | null;
  wildcard_process_contents: "strict" | "lax" | "skip" | null;
  annotation: Annotation | null;
}

export interface ElementDecl {
  id: string;
  name: string | null;
  qname: QName | null;
  ref: QName | null;
  type_name: QName | null;
  type_inline_simple: SimpleType | null;
  type_inline_complex: ComplexType | null;
  min_occurs: number;
  max_occurs: number | "unbounded";
  default: string | null;
  fixed: string | null;
  nillable: boolean;
  abstract: boolean;
  substitution_group: QName | null;
  form: "qualified" | "unqualified" | null;
  target_namespace: string | null;
  is_global: boolean;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export type ComplexDerivationKind = "none" | "restriction" | "extension";
export type ComplexContentKind = "empty" | "simple" | "complex" | "mixed";

export interface ComplexType {
  id: string;
  name: string | null;
  anonymous: boolean;
  abstract: boolean;
  mixed: boolean;
  content_kind: ComplexContentKind;
  derivation: ComplexDerivationKind;
  base: QName | null;
  particle: Particle | null;
  attributes: AttributeDecl[];
  attribute_group_refs: QName[];
  simple_content_base: QName | null;
  simple_content_facets: Facet[];
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export interface Group {
  id: string;
  name: string | null;
  ref: QName | null;
  particle: Particle | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export interface SourceFile {
  id: string;
  filename: string;
  target_namespace: string | null;
  relationship: "main" | "include" | "import" | "redefine" | "override";
  content: string | null;
}

export interface SchemaModel {
  schema_id: string;
  target_namespace: string | null;
  namespaces: Record<string, string>;
  element_form_default: "qualified" | "unqualified";
  attribute_form_default: "qualified" | "unqualified";
  elements: ElementDecl[];
  attributes: AttributeDecl[];
  simple_types: SimpleType[];
  complex_types: ComplexType[];
  groups: Group[];
  attribute_groups: AttributeGroup[];
  files: SourceFile[];
  diagnostics: Diagnostic[];
}

export interface SchemaResponse {
  schema_id: string;
  model: SchemaModel;
}

// Union of things selectable in the viewer.
export type SchemaNodeKind =
  | "element"
  | "attribute"
  | "complexType"
  | "simpleType"
  | "group"
  | "attributeGroup";

export type SchemaNode =
  | ElementDecl
  | AttributeDecl
  | ComplexType
  | SimpleType
  | Group
  | AttributeGroup;

export interface NodeIndexEntry {
  id: string;
  kind: SchemaNodeKind;
  label: string;
  qname: string | null;
  source_ref: SourceRef | null;
  node: SchemaNode;
}
