"""Typed model describing the contents of an XSD schema.

This model is serialized to JSON and consumed by the React frontend. Shape
is intentionally verbose so every piece of XSD information the user expects
(facets, restrictions, annotations, appinfo, comments, source locations) is
preserved explicitly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

QName = str  # serialized as "prefix:local" or "local"


class SourceRef(BaseModel):
    """Where in the uploaded material a declaration came from."""

    model_config = ConfigDict(frozen=True)

    file_id: str
    line: int | None = None


class DocumentationFragment(BaseModel):
    lang: str | None = None
    text: str
    source: Literal["documentation", "comment"] = "documentation"


class AppInfo(BaseModel):
    source_uri: str | None = None
    raw_xml: str


class Annotation(BaseModel):
    documentation: list[DocumentationFragment] = Field(default_factory=list)
    appinfo: list[AppInfo] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.documentation or self.appinfo or self.comments)


class Diagnostic(BaseModel):
    severity: Literal["warning", "error"]
    message: str
    file_id: str | None = None
    line: int | None = None


# ---------------------------------------------------------------------------
# XSD 1.1 shared infrastructure
# ---------------------------------------------------------------------------

XsdVersion = Literal["1.0", "1.1", "unknown"]


class VersionConstraints(BaseModel):
    """Conditional inclusion attributes from the XSD versioning vocabulary
    (``http://www.w3.org/2007/XMLSchema-versioning``). Display-only — the
    parser does not act on these to filter components."""

    min_version: str | None = None
    max_version: str | None = None
    type_available: str | None = None
    type_unavailable: str | None = None
    facet_available: str | None = None
    facet_unavailable: str | None = None


class Wildcard(BaseModel):
    """Open-content / xs:any wildcard. Reused by ``OpenContent`` (Phase 4)
    and richer wildcard rendering. The legacy ``Particle.wildcard_*`` fields
    remain populated for back-compat with the existing renderer."""

    namespace: str | None = None
    not_namespace: str | None = None
    not_qname: str | None = None
    process_contents: Literal["strict", "lax", "skip"] | None = None
    annotation: Annotation | None = None


class Assertion(BaseModel):
    """An XSD 1.1 assertion (``xs:assert`` on complex types, ``xs:assertion``
    on simple types). Display-only — the viewer stores the raw XPath 2.0
    expression but never evaluates it."""

    test: str
    xpath_default_namespace: str | None = None
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------

FacetKind = Literal[
    "enumeration",
    "pattern",
    "length",
    "minLength",
    "maxLength",
    "minInclusive",
    "maxInclusive",
    "minExclusive",
    "maxExclusive",
    "totalDigits",
    "fractionDigits",
    "whiteSpace",
    # Retained for type stability; the parser no longer emits "assertion" as
    # of Phase 2 (assertions live on SimpleType.assertions / ComplexType.assertions).
    "assertion",
    "explicitTimezone",
]


class Facet(BaseModel):
    kind: FacetKind
    value: str
    fixed: bool = False
    annotation: Annotation | None = None
    version_constraints: VersionConstraints | None = None


# ---------------------------------------------------------------------------
# Simple types
# ---------------------------------------------------------------------------

SimpleTypeDerivation = Literal["restriction", "list", "union", "atomic"]


class SimpleType(BaseModel):
    id: str
    name: str | None = None  # None for anonymous inline types
    anonymous: bool = False
    derivation: SimpleTypeDerivation
    base: QName | None = None
    item_type: QName | None = None
    item_inline: SimpleType | None = None
    member_types: list[QName] = Field(default_factory=list)
    member_inline: list[SimpleType] = Field(default_factory=list)
    facets: list[Facet] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


# ---------------------------------------------------------------------------
# Attributes, elements, content model
# ---------------------------------------------------------------------------

AttributeUse = Literal["required", "optional", "prohibited"]


class AttributeDecl(BaseModel):
    id: str
    name: str | None = None
    qname: QName | None = None
    ref: QName | None = None
    type_name: QName | None = None
    type_inline: SimpleType | None = None
    use: AttributeUse = "optional"
    default: str | None = None
    fixed: str | None = None
    form: Literal["qualified", "unqualified"] | None = None
    target_namespace: str | None = None
    is_global: bool = False
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None
    inheritable: bool = False  # XSD 1.1 ``@inheritable`` on xs:attribute


class AttributeGroup(BaseModel):
    id: str
    name: str | None = None
    ref: QName | None = None
    attributes: list[AttributeDecl] = Field(default_factory=list)
    attribute_group_refs: list[QName] = Field(default_factory=list)
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


ParticleKind = Literal[
    "element",
    "group-ref",
    "sequence",
    "choice",
    "all",
    "any",
]


class Particle(BaseModel):
    """A member of a content-model group.

    A Particle is either a concrete element declaration, a reference to a
    named model group, or a nested compositor (sequence/choice/all) that in
    turn contains more particles. An `any` wildcard is also modelled here.
    """

    kind: ParticleKind
    min_occurs: int = 1
    max_occurs: int | Literal["unbounded"] = 1
    element: ElementDecl | None = None
    group_ref: QName | None = None
    group_inline: Group | None = None
    children: list[Particle] = Field(default_factory=list)
    wildcard_namespace: str | None = None
    wildcard_process_contents: Literal["strict", "lax", "skip"] | None = None
    annotation: Annotation | None = None
    version_constraints: VersionConstraints | None = None


class ElementDecl(BaseModel):
    id: str
    name: str | None = None
    qname: QName | None = None
    ref: QName | None = None
    # Identifier of the global declaration ``ref`` points at, in the canonical
    # ``element:{namespace}Local`` form — the prefix is expanded through the
    # namespace declarations in scope, so a ref into an imported namespace
    # (``ds:Signature``) resolves like any local one. ``None`` when the
    # declaration has no ``ref`` or the prefix is undeclared.
    ref_id: str | None = None
    type_name: QName | None = None
    type_inline_simple: SimpleType | None = None
    type_inline_complex: ComplexType | None = None
    min_occurs: int = 1
    max_occurs: int | Literal["unbounded"] = 1
    default: str | None = None
    fixed: str | None = None
    nillable: bool = False
    abstract: bool = False
    substitution_group: QName | None = None
    form: Literal["qualified", "unqualified"] | None = None
    target_namespace: str | None = None
    is_global: bool = False
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None
    alternatives: list[Alternative] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Complex types and groups
# ---------------------------------------------------------------------------

ComplexDerivationKind = Literal["none", "restriction", "extension"]
ComplexContentKind = Literal["empty", "simple", "complex", "mixed"]


class ComplexType(BaseModel):
    id: str
    name: str | None = None
    anonymous: bool = False
    abstract: bool = False
    mixed: bool = False
    content_kind: ComplexContentKind = "empty"
    derivation: ComplexDerivationKind = "none"
    base: QName | None = None
    particle: Particle | None = None
    attributes: list[AttributeDecl] = Field(default_factory=list)
    attribute_group_refs: list[QName] = Field(default_factory=list)
    simple_content_base: QName | None = None  # when content_kind == "simple"
    simple_content_facets: list[Facet] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    open_content: OpenContent | None = None  # XSD 1.1 xs:openContent
    # XSD 1.1: when ``SchemaModel.default_attributes`` is set, this flag
    # determines whether the implicit attribute group applies. Defaults to
    # ``True`` per the spec; complexTypes opt out by writing
    # ``defaultAttributesApply="false"``.
    default_attributes_apply: bool = True
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


class Group(BaseModel):
    id: str
    name: str | None = None
    ref: QName | None = None
    particle: Particle | None = None
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


class Alternative(BaseModel):
    """An XSD 1.1 ``xs:alternative`` — conditional type assignment on an
    element. ``test`` is the raw XPath 2.0 predicate; when ``test`` is
    ``None`` this is the default branch (no ``test`` attribute, picked when
    no other alternative matches). The chosen type is either named
    (``type_name``) or anonymous (``type_inline_simple`` /
    ``type_inline_complex``). Display-only — the predicate is never
    evaluated."""

    test: str | None = None
    type_name: QName | None = None
    type_inline_simple: SimpleType | None = None
    type_inline_complex: ComplexType | None = None
    xpath_default_namespace: str | None = None
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


# ---------------------------------------------------------------------------
# Files and top-level schema
# ---------------------------------------------------------------------------


OverrideKind = Literal[
    "element",
    "attribute",
    "simpleType",
    "complexType",
    "group",
    "attributeGroup",
    "notation",
]


class OverrideReplacement(BaseModel):
    """A single component declared inside an XSD 1.1 ``xs:override`` block.

    Replacements coexist in the model alongside the originals from the
    overridden file (display-only — the viewer does not silently rewrite
    components). ``replacement_id`` is the id of the parsed declaration
    in the corresponding ``SchemaModel`` list.
    """

    kind: OverrideKind
    qname: QName
    replacement_id: str
    source_ref: SourceRef | None = None


class OverrideDirective(BaseModel):
    """One ``xs:override`` block. Records which file is being overridden
    and the replacement declarations that the block contributes."""

    target_file_id: str
    replacements: list[OverrideReplacement] = Field(default_factory=list)
    source_ref: SourceRef | None = None


class SourceFile(BaseModel):
    id: str
    filename: str
    target_namespace: str | None = None
    relationship: Literal["main", "include", "import", "redefine", "override"] = "main"
    content: str | None = None  # populated for text view; optional if too large


class SchemaModel(BaseModel):
    schema_id: str
    target_namespace: str | None = None
    namespaces: dict[str, str] = Field(default_factory=dict)  # prefix -> uri
    element_form_default: Literal["qualified", "unqualified"] = "unqualified"
    attribute_form_default: Literal["qualified", "unqualified"] = "unqualified"
    elements: list[ElementDecl] = Field(default_factory=list)
    attributes: list[AttributeDecl] = Field(default_factory=list)
    simple_types: list[SimpleType] = Field(default_factory=list)
    complex_types: list[ComplexType] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    attribute_groups: list[AttributeGroup] = Field(default_factory=list)
    files: list[SourceFile] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    # XSD 1.1 schema-level information. ``xsd_version`` is heuristic — see
    # XsdParser.parse() for the inference rules.
    xsd_version: XsdVersion = "unknown"
    xpath_default_namespace: str | None = None
    default_attributes: QName | None = None
    default_open_content: OpenContent | None = None
    # XSD 1.1 ``xs:override`` directives. Originals stay where they were —
    # replacements are added to the same lists with distinct ids and cross-
    # referenced through this list. Display-only — the viewer does not merge.
    overrides: list[OverrideDirective] = Field(default_factory=list)


class OpenContent(BaseModel):
    """``xs:openContent`` / ``xs:defaultOpenContent`` (XSD 1.1). Display-only.

    The shape is finalised in Phase 4; defining it here so ``SchemaModel``
    can reference it without a follow-up rebuild dance once Phase 4 lands.
    """

    mode: Literal["interleave", "suffix", "none"] = "interleave"
    applies_to_empty: bool = False
    wildcard: Wildcard | None = None
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


# Resolve forward references
SimpleType.model_rebuild()
ElementDecl.model_rebuild()
Particle.model_rebuild()
ComplexType.model_rebuild()
SchemaModel.model_rebuild()
