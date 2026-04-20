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
    "assertion",
    "explicitTimezone",
]


class Facet(BaseModel):
    kind: FacetKind
    value: str
    fixed: bool = False
    annotation: Annotation | None = None


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
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None


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


class AttributeGroup(BaseModel):
    id: str
    name: str | None = None
    ref: QName | None = None
    attributes: list[AttributeDecl] = Field(default_factory=list)
    attribute_group_refs: list[QName] = Field(default_factory=list)
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None


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


class ElementDecl(BaseModel):
    id: str
    name: str | None = None
    qname: QName | None = None
    ref: QName | None = None
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
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None


class Group(BaseModel):
    id: str
    name: str | None = None
    ref: QName | None = None
    particle: Particle | None = None
    annotation: Annotation | None = None
    source_ref: SourceRef | None = None


# ---------------------------------------------------------------------------
# Files and top-level schema
# ---------------------------------------------------------------------------


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


# Resolve forward references
SimpleType.model_rebuild()
ElementDecl.model_rebuild()
Particle.model_rebuild()
ComplexType.model_rebuild()
