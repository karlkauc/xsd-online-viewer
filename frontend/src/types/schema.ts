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

// XSD 1.1 conditional-inclusion vocabulary (vc:*). Display-only.
export interface VersionConstraints {
  min_version: string | null;
  max_version: string | null;
  type_available: string | null;
  type_unavailable: string | null;
  facet_available: string | null;
  facet_unavailable: string | null;
}

// XSD 1.1 wildcard shape — reused by OpenContent (Phase 4) and richer
// xs:any rendering.
export interface Wildcard {
  namespace: string | null;
  not_namespace: string | null;
  not_qname: string | null;
  process_contents: "strict" | "lax" | "skip" | null;
  annotation: Annotation | null;
}

export type XsdVersion = "1.0" | "1.1" | "unknown";

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
  // Retained for type stability; backend stops emitting it as of Phase 2.
  | "assertion"
  | "explicitTimezone";

export interface Facet {
  kind: FacetKind;
  value: string;
  fixed: boolean;
  annotation: Annotation | null;
  version_constraints?: VersionConstraints | null;
}

// XSD 1.1 ``xs:assert`` (on complex types) and ``xs:assertion`` (on simple
// types). Stored as the raw XPath 2.0 text; never evaluated.
export interface Assertion {
  test: string;
  xpath_default_namespace: string | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
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
  version_constraints?: VersionConstraints | null;
  assertions?: Assertion[];
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
  version_constraints?: VersionConstraints | null;
  inheritable?: boolean;
}

export interface AttributeGroup {
  id: string;
  name: string | null;
  ref: QName | null;
  attributes: AttributeDecl[];
  attribute_group_refs: QName[];
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
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
  version_constraints?: VersionConstraints | null;
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
  version_constraints?: VersionConstraints | null;
  alternatives?: Alternative[];
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
  version_constraints?: VersionConstraints | null;
  assertions?: Assertion[];
  open_content?: OpenContent | null;
  default_attributes_apply?: boolean;
}

export interface Group {
  id: string;
  name: string | null;
  ref: QName | null;
  particle: Particle | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
}

// XSD 1.1 ``xs:alternative`` — conditional type assignment. ``test`` is
// the raw XPath 2.0 predicate; ``test === null`` marks the default branch.
export interface Alternative {
  test: string | null;
  type_name: QName | null;
  type_inline_simple: SimpleType | null;
  type_inline_complex: ComplexType | null;
  xpath_default_namespace: string | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
}

// XSD 1.1 ``xs:openContent`` / ``xs:defaultOpenContent``. Display-only.
export interface OpenContent {
  mode: "interleave" | "suffix" | "none";
  applies_to_empty: boolean;
  wildcard: Wildcard | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
}

export interface SourceFile {
  id: string;
  filename: string;
  target_namespace: string | null;
  relationship: "main" | "include" | "import" | "redefine" | "override";
  content: string | null;
}

export type OverrideKind =
  | "element"
  | "attribute"
  | "simpleType"
  | "complexType"
  | "group"
  | "attributeGroup"
  | "notation";

// XSD 1.1 ``xs:override`` — display-only. Originals stay where they were
// declared; replacements coexist with them in the same SchemaModel lists,
// distinguished by id and cross-referenced via ``OverrideDirective``.
export interface OverrideReplacement {
  kind: OverrideKind;
  qname: QName;
  replacement_id: string;
  source_ref: SourceRef | null;
}

export interface OverrideDirective {
  target_file_id: string;
  replacements: OverrideReplacement[];
  source_ref: SourceRef | null;
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
  // XSD 1.1 schema-level information. All optional in TS so existing test
  // fixtures continue to compile; the backend always emits these fields.
  xsd_version?: XsdVersion;
  xpath_default_namespace?: string | null;
  default_attributes?: QName | null;
  default_open_content?: OpenContent | null;
  overrides?: OverrideDirective[];
}

export interface SchemaResponse {
  schema_id: string;
  model: SchemaModel;
}

// --- XML validation against the loaded schema ---------------------------
// Mirrors backend/app/parser/validation.py. Contract: `reformatted_xml` is
// the authoritative text; every `ValidationErrorItem.line` is 1-based and
// indexes into `reformatted_xml.split("\n")`. The frontend derives the ±1
// context window by slicing that array. When `reformatted_xml` is null the
// input was not well-formed and there is no reformatted text.

export interface XsdRef {
  id: string;
  file_id: string;
  line: number | null;
  qname: string;
}

export interface ValidationErrorItem {
  line: number | null;
  column: number | null;
  message: string;
  severity: "fatal" | "error" | "warning";
  type_name: string | null;
  domain: string | null;
  path: string | null;
  kind: "not-well-formed" | "schema-validation";
  xsd_ref: XsdRef | null;
}

export interface ValidationResponse {
  schema_id: string;
  is_valid: boolean;
  reformatted_xml: string | null;
  errors: ValidationErrorItem[];
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
