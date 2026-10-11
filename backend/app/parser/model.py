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

# The XSD namespace itself. Lives here (rather than in xsd_parser.py, its
# original home) so idroles.py can import it without creating a circular
# import between xsd_parser.py and idroles.py.
XSD_NS = "http://www.w3.org/2001/XMLSchema"

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
    # The ``source`` attribute of xs:documentation: a URI to read more at.
    source_uri: str | None = None
    # None for an annotation of the component itself; otherwise the inner
    # element it is written on ("restriction", "extension", "field",
    # "import other.xsd", …), which has no node of its own in the model.
    context: str | None = None


class AppInfo(BaseModel):
    source_uri: str | None = None
    raw_xml: str
    context: str | None = None  # as on DocumentationFragment


class ForeignAttribute(BaseModel):
    """An attribute from a namespace other than XSD's, which the schema for
    schemas allows on every element and a processor ignores (``jaxb:…``,
    ``sch:…``, ``xml:lang``). ``vc:*`` is not among them: see ``VersionConstraints``."""

    namespace: str
    name: str  # local name
    qname: str  # as written, prefix included
    value: str


class Annotation(BaseModel):
    documentation: list[DocumentationFragment] = Field(default_factory=list)
    appinfo: list[AppInfo] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    # The annotated element's own ``id`` attribute and foreign attributes; XSD
    # counts the latter among a component's annotations.
    xml_id: str | None = None
    attributes: list[ForeignAttribute] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.documentation or self.appinfo or self.comments or self.xml_id or self.attributes
        )


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
    (``http://www.w3.org/2007/XMLSchema-versioning``).

    The parser evaluates them as an XSD 1.1 processor does and leaves out what
    they exclude, so the ones in the model are conditions that hold."""

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


IdentityConstraintKind = Literal["key", "keyref", "unique"]


class IdentityConstraint(BaseModel):
    """An XSD identity constraint (``xs:key``, ``xs:keyref``, ``xs:unique``).

    ``selector``/``fields`` are XPath 1.0 expressions taken verbatim —
    display-only, the viewer never evaluates them against an instance
    document. ``refer``/``refer_id`` only apply to ``kind == "keyref"``:
    ``refer`` is the raw ``refer`` QName as written, ``refer_id`` is the id
    of the ``key``/``unique`` constraint it resolves to, filled in by the
    ``identity.link_keyrefs`` post-pass once every element has been parsed.
    """

    id: str
    kind: IdentityConstraintKind
    name: str
    qname: QName
    selector: str
    fields: list[str] = Field(default_factory=list)
    # Per field, the xpathDefaultNamespace in effect for it (its own, else as
    # for the selector). Same length as ``fields``.
    field_xpath_default_namespaces: list[str | None] = Field(default_factory=list)
    refer: QName | None = None
    refer_id: str | None = None
    # In effect for the selector: its own, else the declaring file's.
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
    # Derivations ``final`` rules out (restriction, list, union, extension),
    # with ``#all`` expanded and the file's ``finalDefault`` applied.
    final: list[str] = Field(default_factory=list)
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None


# ---------------------------------------------------------------------------
# Attributes, elements, content model
# ---------------------------------------------------------------------------

AttributeUse = Literal["required", "optional", "prohibited"]

# ID/IDREF role a declaration's type resolves to, computed by the
# ``idroles.apply_id_roles`` post-pass. ``None`` means the type carries no
# ID/IDREF role at all (most declarations).
IdRole = Literal["id", "idref", "idrefs"]


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
    # As on ElementDecl.
    qualified: bool | None = None
    # As on ElementDecl: set on a local attribute only by XSD 1.1 ``targetNamespace``.
    target_namespace: str | None = None
    is_global: bool = False
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None
    inheritable: bool = False  # XSD 1.1 ``@inheritable`` on xs:attribute
    # ID/IDREF role of this attribute's type, set by idroles.apply_id_roles.
    id_role: IdRole | None = None


class AttributeGroup(BaseModel):
    id: str
    name: str | None = None
    ref: QName | None = None
    attributes: list[AttributeDecl] = Field(default_factory=list)
    attribute_group_refs: list[QName] = Field(default_factory=list)
    any_attribute: Wildcard | None = None  # xs:anyAttribute
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
    wildcard_not_namespace: str | None = None  # XSD 1.1
    wildcard_not_qname: str | None = None  # XSD 1.1
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
    # The first head, kept for consumers that predate ``substitution_groups``.
    substitution_group: QName | None = None
    # Every head: XSD 1.1 lets ``substitutionGroup`` list several.
    substitution_groups: list[QName] = Field(default_factory=list)
    # What ``block`` (extension, restriction, substitution) and ``final``
    # (extension, restriction) rule out, with ``#all`` expanded and the file's
    # ``blockDefault`` / ``finalDefault`` applied.
    block: list[str] = Field(default_factory=list)
    final: list[str] = Field(default_factory=list)
    form: Literal["qualified", "unqualified"] | None = None
    # Whether a local declaration's name is in a namespace: its own ``form``,
    # else the ``elementFormDefault`` / ``attributeFormDefault`` of the file
    # that declares it (not the main file's). ``None`` for a global
    # declaration and for a ``ref``, whose name is the global one's.
    qualified: bool | None = None
    # The declaring file's namespace for a global declaration; for a local one
    # only an explicit XSD 1.1 ``targetNamespace`` attribute.
    target_namespace: str | None = None
    is_global: bool = False
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None
    version_constraints: VersionConstraints | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    identity_constraints: list[IdentityConstraint] = Field(default_factory=list)
    # ID/IDREF role of this element's type, set by idroles.apply_id_roles.
    # Always None for a ``ref`` particle — the frontend resolves the role
    # through the target of ``resolveElementRef``.
    id_role: IdRole | None = None


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
    any_attribute: Wildcard | None = None  # xs:anyAttribute
    simple_content_base: QName | None = None  # when content_kind == "simple"
    simple_content_facets: list[Facet] = Field(default_factory=list)
    # <xs:simpleContent><xs:restriction base="…"><xs:simpleType>…: the anonymous
    # type that replaces the base's content type before the facets apply.
    simple_content_inline: SimpleType | None = None
    # xs:assert, and the xs:assertion facets of a simpleContent restriction.
    assertions: list[Assertion] = Field(default_factory=list)
    # As on ElementDecl; both take extension and restriction.
    block: list[str] = Field(default_factory=list)
    final: list[str] = Field(default_factory=list)
    open_content: OpenContent | None = None  # XSD 1.1 xs:openContent
    # XSD 1.1: when ``SchemaModel.default_attributes`` is set, this flag
    # determines whether the implicit attribute group applies. Defaults to
    # ``True`` per the spec; complexTypes opt out by writing
    # ``defaultAttributesApply="false"``.
    default_attributes_apply: bool = True
    # The attribute group this type gets through its own file's
    # ``defaultAttributes`` (as written there), or None when the file names
    # none or the type opted out. Not repeated in ``attribute_group_refs``.
    default_attributes: QName | None = None
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

    Applied as XSD 1.1 defines it: the replacement stands in for the
    component of the same kind and name in the overridden file, which is left
    out of the model. ``replacement_id`` is the id of the parsed declaration
    in the corresponding ``SchemaModel`` list — the ordinary id of that name —
    and ``original_source_ref`` is where the definition it replaced is written.
    A component in the block that replaces nothing is ignored, as the
    specification says, and reported as a diagnostic.
    """

    kind: OverrideKind
    qname: QName
    replacement_id: str
    source_ref: SourceRef | None = None
    original_source_ref: SourceRef | None = None


class OverrideDirective(BaseModel):
    """One ``xs:override`` block. Records which file is being overridden
    and the replacement declarations that the block contributes."""

    target_file_id: str
    replacements: list[OverrideReplacement] = Field(default_factory=list)
    source_ref: SourceRef | None = None


class Notation(BaseModel):
    """An ``xs:notation`` declaration."""

    id: str
    name: str
    qname: QName
    public: str | None = None
    system: str | None = None
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None


RedefineKind = Literal["simpleType", "complexType", "group", "attributeGroup"]


class Redefinition(BaseModel):
    """A single component declared inside an ``xs:redefine`` block.

    Unlike ``xs:override`` this is applied, not just displayed: the
    redefinition takes over the component's name and id, so every reference
    to the name reaches it. The definition it replaces stays in the same
    ``SchemaModel`` list under a ``Name~original`` name (``~`` cannot occur
    in a real XSD name), and the redefinition's reference to itself — its
    ``base``, or the group's ``ref`` to itself — is rewritten to that name.
    ``original_id`` is ``None`` when the redefined file defines no such
    component (it did not load, or the schema is wrong).
    """

    kind: RedefineKind
    qname: QName
    redefinition_id: str
    original_id: str | None = None
    source_ref: SourceRef | None = None


class RedefineDirective(BaseModel):
    """One ``xs:redefine`` block and the components it redefines.
    ``target_file_id`` is ``None`` when the redefined file did not load."""

    target_file_id: str | None = None
    redefinitions: list[Redefinition] = Field(default_factory=list)
    source_ref: SourceRef | None = None


class SourceFile(BaseModel):
    id: str
    filename: str
    target_namespace: str | None = None
    relationship: Literal["main", "include", "import", "redefine", "override"] = "main"
    # This file's own defaults; ``SchemaModel`` carries the main file's.
    element_form_default: Literal["qualified", "unqualified"] = "unqualified"
    attribute_form_default: Literal["qualified", "unqualified"] = "unqualified"
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
    notations: list[Notation] = Field(default_factory=list)
    # The main file's own xs:schema: its annotations and ``version`` attribute.
    annotation: Annotation | None = None
    schema_version: str | None = None
    files: list[SourceFile] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    # XSD 1.1 schema-level information. ``xsd_version`` is heuristic — see
    # XsdParser.parse() for the inference rules.
    xsd_version: XsdVersion = "unknown"
    xpath_default_namespace: str | None = None
    default_attributes: QName | None = None
    default_open_content: OpenContent | None = None
    # XSD 1.1 ``xs:override`` directives, applied to the lists above — see
    # ``OverrideReplacement``.
    overrides: list[OverrideDirective] = Field(default_factory=list)
    # ``xs:redefine`` blocks, applied to the lists above — see ``Redefinition``.
    redefines: list[RedefineDirective] = Field(default_factory=list)


class OpenContent(BaseModel):
    """``xs:openContent`` / ``xs:defaultOpenContent`` (XSD 1.1).

    ``ComplexType.open_content`` is the one in effect: ``origin`` says whether
    the type wrote it itself, got it from its file's ``xs:defaultOpenContent``,
    or inherits it from the type it extends.
    """

    mode: Literal["interleave", "suffix", "none"] = "interleave"
    origin: Literal["own", "default", "base"] = "own"
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
