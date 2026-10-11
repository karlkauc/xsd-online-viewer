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
  // The ``source`` attribute of xs:documentation.
  source_uri?: string | null;
  // Set when the annotation is written on an inner element without a node of
  // its own ("restriction", "extension", "field", "import other.xsd", …).
  context?: string | null;
}

export interface AppInfo {
  source_uri: string | null;
  raw_xml: string;
  context?: string | null;
}

// An attribute from a namespace other than XSD's (jaxb:…, sch:…, xml:lang).
export interface ForeignAttribute {
  namespace: string;
  name: string;
  qname: string;
  value: string;
}

export interface Annotation {
  documentation: DocumentationFragment[];
  appinfo: AppInfo[];
  comments: string[];
  // The annotated element's own ``id`` attribute and foreign attributes.
  xml_id?: string | null;
  attributes?: ForeignAttribute[];
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

// XSD identity constraints (``xs:key`` / ``xs:keyref`` / ``xs:unique``).
// ``selector``/``fields`` are XPath 1.0 expressions taken verbatim —
// display-only, the viewer never evaluates them against an instance
// document. ``refer``/``refer_id`` only apply to ``kind === "keyref"``.
export type IdentityConstraintKind = "key" | "keyref" | "unique";

export interface IdentityConstraint {
  id: string;
  kind: IdentityConstraintKind;
  name: string;
  qname: QName;
  selector: string;
  fields: string[];
  // Per field, the xpathDefaultNamespace in effect for it.
  field_xpath_default_namespaces?: (string | null)[];
  refer: QName | null;
  refer_id: string | null;
  xpath_default_namespace: string | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints: VersionConstraints | null;
}

// ID/IDREF role a declaration's type resolves to, computed by the backend's
// ``idroles.apply_id_roles`` post-pass. ``undefined``/``null`` means the
// type carries no ID/IDREF role at all (most declarations).
export type IdRole = "id" | "idref" | "idrefs";

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
  final?: string[];
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
  // Whether a local declaration's name is in a namespace: its own `form`,
  // else the declaring file's form default. null for a global declaration
  // and for a `ref`.
  qualified?: boolean | null;
  target_namespace: string | null;
  is_global: boolean;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
  inheritable?: boolean;
  id_role?: IdRole | null;
}

export interface AttributeGroup {
  id: string;
  name: string | null;
  ref: QName | null;
  attributes: AttributeDecl[];
  attribute_group_refs: QName[];
  any_attribute?: Wildcard | null;
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
  wildcard_not_namespace?: string | null;
  wildcard_not_qname?: string | null;
  annotation: Annotation | null;
  version_constraints?: VersionConstraints | null;
}

export interface ElementDecl {
  id: string;
  name: string | null;
  qname: QName | null;
  ref: QName | null;
  // Id of the global declaration `ref` points at (canonical
  // `element:{namespace}Local` form, prefix already expanded by the parser),
  // so a ref into an imported namespace resolves like any local one.
  ref_id?: string | null;
  type_name: QName | null;
  type_inline_simple: SimpleType | null;
  type_inline_complex: ComplexType | null;
  min_occurs: number;
  max_occurs: number | "unbounded";
  default: string | null;
  fixed: string | null;
  nillable: boolean;
  abstract: boolean;
  // The first head; ``substitution_groups`` has all of them (XSD 1.1).
  substitution_group: QName | null;
  substitution_groups?: QName[];
  // Derivations ruled out by ``block`` / ``final``, schema defaults applied.
  block?: string[];
  final?: string[];
  form: "qualified" | "unqualified" | null;
  // Whether a local declaration's name is in a namespace: its own `form`,
  // else the declaring file's form default. null for a global declaration
  // and for a `ref`.
  qualified?: boolean | null;
  target_namespace: string | null;
  is_global: boolean;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
  alternatives?: Alternative[];
  identity_constraints?: IdentityConstraint[];
  id_role?: IdRole | null;
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
  any_attribute?: Wildcard | null;
  block?: string[];
  final?: string[];
  simple_content_base: QName | null;
  simple_content_facets: Facet[];
  simple_content_inline?: SimpleType | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
  version_constraints?: VersionConstraints | null;
  assertions?: Assertion[];
  open_content?: OpenContent | null;
  default_attributes_apply?: boolean;
  // The attribute group from the declaring file's ``defaultAttributes``, when it applies.
  default_attributes?: QName | null;
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

// XSD 1.1 ``xs:openContent`` / ``xs:defaultOpenContent``. On a complex type
// it is the one in effect; ``origin`` says where it comes from (the type
// itself, its file's xs:defaultOpenContent, or the type it extends).
export interface OpenContent {
  mode: "interleave" | "suffix" | "none";
  origin?: "own" | "default" | "base";
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
  // This file's own defaults; SchemaModel carries the main file's.
  element_form_default?: "qualified" | "unqualified";
  attribute_form_default?: "qualified" | "unqualified";
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

// XSD 1.1 ``xs:override``, applied by the parser: the replacement stands in
// the SchemaModel lists under the component's ordinary id, the definition it
// replaced is left out and only reachable as source (``original_source_ref``).
export interface OverrideReplacement {
  kind: OverrideKind;
  qname: QName;
  replacement_id: string;
  source_ref: SourceRef | null;
  original_source_ref?: SourceRef | null;
}

export interface OverrideDirective {
  target_file_id: string;
  replacements: OverrideReplacement[];
  source_ref: SourceRef | null;
}

export interface Notation {
  id: string;
  name: string;
  qname: QName;
  public: string | null;
  system: string | null;
  annotation: Annotation | null;
  source_ref: SourceRef | null;
}

export type RedefineKind = "simpleType" | "complexType" | "group" | "attributeGroup";

// ``xs:redefine`` — applied by the parser: the redefinition carries the
// component's name and id, the definition it replaces lives on as
// ``Name~original`` and is what the redefinition derives from.
export interface Redefinition {
  kind: RedefineKind;
  qname: QName;
  redefinition_id: string;
  original_id: string | null;
  source_ref: SourceRef | null;
}

export interface RedefineDirective {
  target_file_id: string | null;
  redefinitions: Redefinition[];
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
  redefines?: RedefineDirective[];
  notations?: Notation[];
  // The main file's xs:schema: its annotations and ``version`` attribute.
  annotation?: Annotation | null;
  schema_version?: string | null;
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
  // "libxml2" (XSD 1.0) or "xmlschema" (XSD 1.1: assertions, type alternatives, IDREF targets).
  validator?: "libxml2" | "xmlschema";
}

// Union of things selectable in the viewer.
export type SchemaNodeKind =
  | "element"
  | "attribute"
  | "complexType"
  | "simpleType"
  | "group"
  | "attributeGroup"
  | "notation";

export type SchemaNode =
  | ElementDecl
  | AttributeDecl
  | ComplexType
  | SimpleType
  | Group
  | AttributeGroup
  | Notation;

export interface NodeIndexEntry {
  id: string;
  kind: SchemaNodeKind;
  label: string;
  qname: string | null;
  source_ref: SourceRef | null;
  node: SchemaNode;
}
