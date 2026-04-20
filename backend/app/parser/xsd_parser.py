"""lxml-based XSD parser that produces a :class:`SchemaModel`.

The parser deliberately walks the XSD element tree by hand instead of using
lxml's ``XMLSchema`` validator, because we want to preserve every piece of
authoring information (annotations, appinfo, comments, facets, source
locations) rather than the compiled post-schema validation infoset.
"""

from __future__ import annotations

import hashlib
import logging
import posixpath
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal
from urllib.parse import urljoin, urlparse

from lxml import etree

from app.parser.model import (
    Annotation,
    AppInfo,
    AttributeDecl,
    AttributeGroup,
    ComplexContentKind,
    ComplexDerivationKind,
    ComplexType,
    Diagnostic,
    DocumentationFragment,
    ElementDecl,
    Facet,
    FacetKind,
    Group,
    Particle,
    SchemaModel,
    SimpleType,
    SourceFile,
    SourceRef,
)
from app.parser.security import (
    FetchedResource,
    SecurityError,
    fetch_schema_url,
    parse_bytes,
)

logger = logging.getLogger(__name__)

XSD_NS = "http://www.w3.org/2001/XMLSchema"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def _xsd(tag: str) -> str:
    return f"{{{XSD_NS}}}{tag}"


_FACET_TAGS: dict[str, FacetKind] = {
    _xsd("enumeration"): "enumeration",
    _xsd("pattern"): "pattern",
    _xsd("length"): "length",
    _xsd("minLength"): "minLength",
    _xsd("maxLength"): "maxLength",
    _xsd("minInclusive"): "minInclusive",
    _xsd("maxInclusive"): "maxInclusive",
    _xsd("minExclusive"): "minExclusive",
    _xsd("maxExclusive"): "maxExclusive",
    _xsd("totalDigits"): "totalDigits",
    _xsd("fractionDigits"): "fractionDigits",
    _xsd("whiteSpace"): "whiteSpace",
    _xsd("assertion"): "assertion",
    _xsd("explicitTimezone"): "explicitTimezone",
}


# ---------------------------------------------------------------------------
# Schema sources: how to resolve schemaLocation references
# ---------------------------------------------------------------------------


class SchemaResolver:
    """Resolve a schema location (relative or absolute) to XML bytes."""

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        raise NotImplementedError


@dataclass
class ZipResolver(SchemaResolver):
    """Resolves locations against a ZIP archive of uploaded files."""

    files: dict[str, bytes]

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        candidates: list[str] = []
        if base_location:
            base_dir = posixpath.dirname(base_location)
            if base_dir:
                candidates.append(posixpath.normpath(posixpath.join(base_dir, location)))
        candidates.append(posixpath.normpath(location))
        candidates.append(location)
        for name in candidates:
            if name in self.files:
                return name, self.files[name]
            stripped = name.lstrip("./")
            if stripped in self.files:
                return stripped, self.files[stripped]
        # case-insensitive fallback
        lowered = {name.lower(): name for name in self.files}
        for candidate in candidates:
            real = lowered.get(candidate.lower())
            if real is not None:
                return real, self.files[real]
        return None


@dataclass
class UrlResolver(SchemaResolver):
    """Fetches references via HTTP(S), SSRF-hardened."""

    base_url: str | None = None

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        base = base_location or self.base_url
        if not base:
            return None
        absolute = urljoin(base, location)
        if urlparse(absolute).scheme not in ("http", "https"):
            return None
        try:
            fetched: FetchedResource = fetch_schema_url(absolute)
        except SecurityError as exc:
            logger.info(
                "url resolution rejected",
                extra={"ctx_url": absolute, "ctx_reason": str(exc)},
            )
            raise
        return fetched.url, fetched.content


@dataclass
class ChainedResolver(SchemaResolver):
    resolvers: list[SchemaResolver]

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        for resolver in self.resolvers:
            try:
                result = resolver.resolve(base_location, location)
            except SecurityError:
                raise
            if result is not None:
                return result
        return None


# ---------------------------------------------------------------------------
# Loaded file set
# ---------------------------------------------------------------------------


@dataclass
class _LoadedFile:
    file_id: str
    filename: str
    tree: etree._ElementTree
    target_ns: str | None
    relationship: Literal["main", "include", "import", "redefine", "override"]
    raw_content: bytes

    @property
    def root(self) -> etree._Element:
        return self.tree.getroot()


def _namespace_and_local(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return None, tag


def _text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    text = elem.text or ""
    for child in elem:
        text += etree.tostring(child, encoding="unicode")
        if child.tail:
            text += child.tail
    return text


def _bool_attr(elem: etree._Element, name: str, default: bool = False) -> bool:
    raw = elem.get(name)
    if raw is None:
        return default
    return raw.lower() in ("true", "1")


def _occurs(value: str | None, default: int) -> int | Literal["unbounded"]:
    if value is None:
        return default
    if value == "unbounded":
        return "unbounded"
    try:
        return int(value)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


@dataclass
class XsdParseInput:
    main_filename: str
    main_content: bytes
    resolver: SchemaResolver
    allow_url_fallback: bool = False
    base_url: str | None = None


@dataclass
class _BuildState:
    files: list[_LoadedFile] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    by_key: dict[tuple[str | None, str], _LoadedFile] = field(default_factory=dict)
    _id_counter: int = 0

    def next_anon(self) -> int:
        self._id_counter += 1
        return self._id_counter


class XsdParser:
    def __init__(self, inp: XsdParseInput) -> None:
        self.inp = inp
        self.state = _BuildState()

    # ---- loading phase -------------------------------------------------

    def _load(
        self,
        filename: str,
        content: bytes,
        relationship: Literal["main", "include", "import", "redefine", "override"],
        target_ns_hint: str | None,
    ) -> _LoadedFile | None:
        key = (target_ns_hint, filename)
        if key in self.state.by_key:
            return self.state.by_key[key]
        try:
            tree = parse_bytes(content, filename)
        except SecurityError as exc:
            self.state.diagnostics.append(
                Diagnostic(severity="error", message=str(exc), file_id=None)
            )
            return None
        except etree.XMLSyntaxError as exc:
            self.state.diagnostics.append(
                Diagnostic(severity="error", message=f"{filename}: {exc}", file_id=None)
            )
            return None
        root = tree.getroot()
        if _namespace_and_local(root.tag) != (XSD_NS, "schema"):
            self.state.diagnostics.append(
                Diagnostic(
                    severity="error",
                    message=f"{filename}: root element is not xs:schema",
                )
            )
            return None
        target_ns = root.get("targetNamespace") or target_ns_hint
        file_id = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:12]
        loaded = _LoadedFile(
            file_id=file_id,
            filename=filename,
            tree=tree,
            target_ns=target_ns,
            relationship=relationship,
            raw_content=content,
        )
        self.state.files.append(loaded)
        self.state.by_key[key] = loaded
        self._follow_references(loaded)
        return loaded

    def _follow_references(self, loaded: _LoadedFile) -> None:
        mapping: list[tuple[str, Literal["include", "import", "redefine", "override"]]] = [
            ("include", "include"),
            ("import", "import"),
            ("redefine", "redefine"),
            ("override", "override"),
        ]
        for tag, relationship in mapping:
            for elem in loaded.root.findall(f"{{{XSD_NS}}}{tag}"):
                location = elem.get("schemaLocation")
                if not location:
                    continue
                target_ns = elem.get("namespace") if tag == "import" else loaded.target_ns
                try:
                    resolved = self.inp.resolver.resolve(loaded.filename, location)
                except SecurityError as exc:
                    self.state.diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            message=(
                                f"{loaded.filename}: could not load {location!r}: {exc}"
                            ),
                            file_id=loaded.file_id,
                            line=elem.sourceline,
                        )
                    )
                    continue
                if resolved is None:
                    self.state.diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            message=(
                                f"{loaded.filename}: unresolved {tag} "
                                f"schemaLocation={location!r}"
                            ),
                            file_id=loaded.file_id,
                            line=elem.sourceline,
                        )
                    )
                    continue
                ref_filename, ref_bytes = resolved
                self._load(ref_filename, ref_bytes, relationship, target_ns)

    # ---- parsing phase -------------------------------------------------

    def parse(self) -> SchemaModel:
        main = self._load(self.inp.main_filename, self.inp.main_content, "main", None)
        if main is None:
            # Main schema failed to load — every diagnostic collected so far
            # pertains to it, so surface the first as a parse failure.
            first_error = next(
                (d for d in self.state.diagnostics if d.severity == "error"),
                None,
            )
            message = first_error.message if first_error else "failed to parse main schema"
            raise ValueError(message)

        model = SchemaModel(
            schema_id="pending",
            target_namespace=main.target_ns,
            namespaces=_collect_namespaces(self.state.files),
            element_form_default=main.root.get("elementFormDefault", "unqualified"),  # type: ignore[arg-type]
            attribute_form_default=main.root.get("attributeFormDefault", "unqualified"),  # type: ignore[arg-type]
        )

        for loaded in self.state.files:
            source = SourceFile(
                id=loaded.file_id,
                filename=loaded.filename,
                target_namespace=loaded.target_ns,
                relationship=loaded.relationship,
                content=loaded.raw_content.decode("utf-8", errors="replace"),
            )
            model.files.append(source)

            for child in loaded.root:
                if not isinstance(child.tag, str):
                    continue
                self._process_top_level(child, loaded, model)

        model.diagnostics.extend(self.state.diagnostics)
        return model

    def _process_top_level(
        self, elem: etree._Element, loaded: _LoadedFile, model: SchemaModel
    ) -> None:
        _, local = _namespace_and_local(elem.tag)
        if local == "element":
            model.elements.append(self._parse_element(elem, loaded, is_global=True))
        elif local == "attribute":
            model.attributes.append(
                self._parse_attribute(elem, loaded, is_global=True)
            )
        elif local == "simpleType":
            model.simple_types.append(self._parse_simple_type(elem, loaded))
        elif local == "complexType":
            model.complex_types.append(self._parse_complex_type(elem, loaded))
        elif local == "group":
            model.groups.append(self._parse_group(elem, loaded))
        elif local == "attributeGroup":
            model.attribute_groups.append(self._parse_attribute_group(elem, loaded))
        # include/import/redefine/override/annotation/notation — skip here:
        # references were followed in _follow_references; top-level annotation
        # is attached to the schema node but we omit it from the model for now.

    # ---- per-construct parsers ----------------------------------------

    def _parse_element(
        self,
        elem: etree._Element,
        loaded: _LoadedFile,
        *,
        is_global: bool,
    ) -> ElementDecl:
        name = elem.get("name")
        ref = elem.get("ref")
        type_name = elem.get("type")
        annotation = self._collect_annotation(elem)

        type_inline_simple: SimpleType | None = None
        type_inline_complex: ComplexType | None = None
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            _, local = _namespace_and_local(child.tag)
            if local == "simpleType":
                type_inline_simple = self._parse_simple_type(child, loaded)
            elif local == "complexType":
                type_inline_complex = self._parse_complex_type(child, loaded)

        qname = self._compose_qname(loaded, name) if name and is_global else None
        identifier = self._make_id("element", qname or ref or f"anon-{self.state.next_anon()}")

        return ElementDecl(
            id=identifier,
            name=name,
            qname=qname,
            ref=ref,
            type_name=type_name,
            type_inline_simple=type_inline_simple,
            type_inline_complex=type_inline_complex,
            min_occurs=_occurs(elem.get("minOccurs"), 1) if not is_global else 1,
            max_occurs=_occurs(elem.get("maxOccurs"), 1) if not is_global else 1,
            default=elem.get("default"),
            fixed=elem.get("fixed"),
            nillable=_bool_attr(elem, "nillable"),
            abstract=_bool_attr(elem, "abstract"),
            substitution_group=elem.get("substitutionGroup"),
            form=elem.get("form"),  # type: ignore[arg-type]
            target_namespace=loaded.target_ns if is_global else None,
            is_global=is_global,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
        )

    def _parse_attribute(
        self,
        elem: etree._Element,
        loaded: _LoadedFile,
        *,
        is_global: bool,
    ) -> AttributeDecl:
        name = elem.get("name")
        ref = elem.get("ref")
        type_name = elem.get("type")
        annotation = self._collect_annotation(elem)

        type_inline: SimpleType | None = None
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            _, local = _namespace_and_local(child.tag)
            if local == "simpleType":
                type_inline = self._parse_simple_type(child, loaded)

        qname = self._compose_qname(loaded, name) if name and is_global else None
        identifier = self._make_id(
            "attribute", qname or ref or f"anon-{self.state.next_anon()}"
        )

        use = elem.get("use", "optional")
        if use not in ("required", "optional", "prohibited"):
            use = "optional"

        return AttributeDecl(
            id=identifier,
            name=name,
            qname=qname,
            ref=ref,
            type_name=type_name,
            type_inline=type_inline,
            use=use,  # type: ignore[arg-type]
            default=elem.get("default"),
            fixed=elem.get("fixed"),
            form=elem.get("form"),  # type: ignore[arg-type]
            target_namespace=loaded.target_ns if is_global else None,
            is_global=is_global,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
        )

    def _parse_simple_type(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> SimpleType:
        name = elem.get("name")
        anonymous = name is None
        annotation = self._collect_annotation(elem)
        qname = self._compose_qname(loaded, name) if name else f"anon-simple-{self.state.next_anon()}"
        identifier = self._make_id("simpleType", qname)

        restriction = elem.find(_xsd("restriction"))
        list_elem = elem.find(_xsd("list"))
        union = elem.find(_xsd("union"))

        derivation = "atomic"
        base: str | None = None
        facets: list[Facet] = []
        item_type: str | None = None
        item_inline: SimpleType | None = None
        member_types: list[str] = []
        member_inline: list[SimpleType] = []

        if restriction is not None:
            derivation = "restriction"
            base = restriction.get("base")
            inline_base = restriction.find(_xsd("simpleType"))
            if inline_base is not None and base is None:
                member_inline.append(self._parse_simple_type(inline_base, loaded))
            facets = self._parse_facets(restriction)
        elif list_elem is not None:
            derivation = "list"
            item_type = list_elem.get("itemType")
            inline_item = list_elem.find(_xsd("simpleType"))
            if inline_item is not None:
                item_inline = self._parse_simple_type(inline_item, loaded)
        elif union is not None:
            derivation = "union"
            member_types_attr = union.get("memberTypes") or ""
            member_types = [t for t in member_types_attr.split() if t]
            for child in union.findall(_xsd("simpleType")):
                member_inline.append(self._parse_simple_type(child, loaded))

        return SimpleType(
            id=identifier,
            name=name,
            anonymous=anonymous,
            derivation=derivation,  # type: ignore[arg-type]
            base=base,
            facets=facets,
            item_type=item_type,
            item_inline=item_inline,
            member_types=member_types,
            member_inline=member_inline,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
        )

    def _parse_complex_type(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> ComplexType:
        name = elem.get("name")
        anonymous = name is None
        annotation = self._collect_annotation(elem)
        qname = (
            self._compose_qname(loaded, name)
            if name
            else f"anon-complex-{self.state.next_anon()}"
        )
        identifier = self._make_id("complexType", qname)

        mixed = _bool_attr(elem, "mixed")
        abstract = _bool_attr(elem, "abstract")

        derivation: ComplexDerivationKind = "none"
        base: str | None = None
        content_kind: ComplexContentKind = "empty"
        particle: Particle | None = None
        attributes: list[AttributeDecl] = []
        attribute_group_refs: list[str] = []
        simple_content_base: str | None = None
        simple_content_facets: list[Facet] = []

        simple_content = elem.find(_xsd("simpleContent"))
        complex_content = elem.find(_xsd("complexContent"))

        if simple_content is not None:
            content_kind = "simple"
            restr = simple_content.find(_xsd("restriction"))
            ext = simple_content.find(_xsd("extension"))
            inner = restr if restr is not None else ext
            if inner is not None:
                derivation = "restriction" if restr is not None else "extension"
                base = inner.get("base")
                simple_content_base = base
                if restr is not None:
                    simple_content_facets = self._parse_facets(restr)
                attrs, groups = self._parse_attribute_children(inner, loaded)
                attributes.extend(attrs)
                attribute_group_refs.extend(groups)
        elif complex_content is not None:
            content_kind = "mixed" if mixed else "complex"
            restr = complex_content.find(_xsd("restriction"))
            ext = complex_content.find(_xsd("extension"))
            inner = restr if restr is not None else ext
            if inner is not None:
                derivation = "restriction" if restr is not None else "extension"
                base = inner.get("base")
                particle = self._parse_content_model(inner, loaded)
                attrs, groups = self._parse_attribute_children(inner, loaded)
                attributes.extend(attrs)
                attribute_group_refs.extend(groups)
        else:
            particle = self._parse_content_model(elem, loaded)
            if particle is not None:
                content_kind = "mixed" if mixed else "complex"
            attrs, groups = self._parse_attribute_children(elem, loaded)
            attributes.extend(attrs)
            attribute_group_refs.extend(groups)

        return ComplexType(
            id=identifier,
            name=name,
            anonymous=anonymous,
            abstract=abstract,
            mixed=mixed,
            content_kind=content_kind,
            derivation=derivation,
            base=base,
            particle=particle,
            attributes=attributes,
            attribute_group_refs=attribute_group_refs,
            simple_content_base=simple_content_base,
            simple_content_facets=simple_content_facets,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
        )

    def _parse_group(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Group:
        name = elem.get("name")
        ref = elem.get("ref")
        annotation = self._collect_annotation(elem)
        qname = (
            self._compose_qname(loaded, name)
            if name
            else ref or f"anon-group-{self.state.next_anon()}"
        )
        identifier = self._make_id("group", qname)
        particle = self._parse_content_model(elem, loaded)
        return Group(
            id=identifier,
            name=name,
            ref=ref,
            particle=particle,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
        )

    def _parse_attribute_group(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> AttributeGroup:
        name = elem.get("name")
        ref = elem.get("ref")
        annotation = self._collect_annotation(elem)
        qname = (
            self._compose_qname(loaded, name)
            if name
            else ref or f"anon-ag-{self.state.next_anon()}"
        )
        identifier = self._make_id("attributeGroup", qname)
        attributes, group_refs = self._parse_attribute_children(elem, loaded)
        return AttributeGroup(
            id=identifier,
            name=name,
            ref=ref,
            attributes=attributes,
            attribute_group_refs=group_refs,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
        )

    # ---- content model helpers ----------------------------------------

    def _parse_content_model(
        self, parent: etree._Element, loaded: _LoadedFile
    ) -> Particle | None:
        for child in parent:
            if not isinstance(child.tag, str):
                continue
            _, local = _namespace_and_local(child.tag)
            if local in ("sequence", "choice", "all"):
                return self._parse_compositor(child, loaded)
            if local == "group":
                # group as particle inside a complexType/group body
                return self._parse_group_ref_particle(child, loaded)
        return None

    def _parse_compositor(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Particle:
        _, local = _namespace_and_local(elem.tag)
        kind = local  # sequence | choice | all
        particle = Particle(
            kind=kind,  # type: ignore[arg-type]
            min_occurs=_occurs(elem.get("minOccurs"), 1),  # type: ignore[arg-type]
            max_occurs=_occurs(elem.get("maxOccurs"), 1),
            annotation=self._collect_annotation(elem),
        )
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            _, child_local = _namespace_and_local(child.tag)
            if child_local == "element":
                inner = Particle(
                    kind="element",
                    min_occurs=_occurs(child.get("minOccurs"), 1),  # type: ignore[arg-type]
                    max_occurs=_occurs(child.get("maxOccurs"), 1),
                    element=self._parse_element(child, loaded, is_global=False),
                )
                particle.children.append(inner)
            elif child_local in ("sequence", "choice", "all"):
                particle.children.append(self._parse_compositor(child, loaded))
            elif child_local == "group":
                particle.children.append(
                    self._parse_group_ref_particle(child, loaded)
                )
            elif child_local == "any":
                particle.children.append(
                    Particle(
                        kind="any",
                        min_occurs=_occurs(child.get("minOccurs"), 1),  # type: ignore[arg-type]
                        max_occurs=_occurs(child.get("maxOccurs"), 1),
                        wildcard_namespace=child.get("namespace"),
                        wildcard_process_contents=child.get("processContents"),  # type: ignore[arg-type]
                        annotation=self._collect_annotation(child),
                    )
                )
        return particle

    def _parse_group_ref_particle(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Particle:
        ref = elem.get("ref")
        return Particle(
            kind="group-ref",
            min_occurs=_occurs(elem.get("minOccurs"), 1),  # type: ignore[arg-type]
            max_occurs=_occurs(elem.get("maxOccurs"), 1),
            group_ref=ref,
            group_inline=(
                None
                if ref is not None
                else self._parse_group(elem, loaded)
            ),
            annotation=self._collect_annotation(elem),
        )

    def _parse_attribute_children(
        self, parent: etree._Element, loaded: _LoadedFile
    ) -> tuple[list[AttributeDecl], list[str]]:
        attributes: list[AttributeDecl] = []
        group_refs: list[str] = []
        for child in parent:
            if not isinstance(child.tag, str):
                continue
            _, local = _namespace_and_local(child.tag)
            if local == "attribute":
                attributes.append(
                    self._parse_attribute(child, loaded, is_global=False)
                )
            elif local == "attributeGroup":
                ref = child.get("ref")
                if ref is not None:
                    group_refs.append(ref)
        return attributes, group_refs

    # ---- facets and annotations ---------------------------------------

    def _parse_facets(self, restriction: etree._Element) -> list[Facet]:
        facets: list[Facet] = []
        for child in restriction:
            if not isinstance(child.tag, str):
                continue
            kind = _FACET_TAGS.get(child.tag)
            if kind is None:
                continue
            facets.append(
                Facet(
                    kind=kind,
                    value=child.get("value", ""),
                    fixed=_bool_attr(child, "fixed"),
                    annotation=self._collect_annotation(child),
                )
            )
        return facets

    def _collect_annotation(self, elem: etree._Element) -> Annotation | None:
        documentation: list[DocumentationFragment] = []
        appinfo: list[AppInfo] = []
        for child in elem.findall(_xsd("annotation")):
            for sub in child:
                if not isinstance(sub.tag, str):
                    continue
                _, local = _namespace_and_local(sub.tag)
                if local == "documentation":
                    documentation.append(
                        DocumentationFragment(
                            lang=sub.get(f"{{{XML_NS}}}lang"),
                            text=_text(sub).strip(),
                        )
                    )
                elif local == "appinfo":
                    appinfo.append(
                        AppInfo(
                            source_uri=sub.get("source"),
                            raw_xml=etree.tostring(sub, encoding="unicode").strip(),
                        )
                    )
        comments: list[str] = []
        prev = elem.getprevious()
        while prev is not None and isinstance(prev, etree._Comment):
            comments.append(prev.text or "")
            prev = prev.getprevious()
        comments.reverse()
        if not documentation and not appinfo and not comments:
            return None
        return Annotation(documentation=documentation, appinfo=appinfo, comments=comments)

    # ---- identifier helpers -------------------------------------------

    def _compose_qname(self, loaded: _LoadedFile, local: str) -> str:
        if loaded.target_ns:
            return f"{{{loaded.target_ns}}}{local}"
        return local

    def _make_id(self, kind: str, qname: str) -> str:
        return f"{kind}:{qname}"


def _collect_namespaces(files: list[_LoadedFile]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for f in files:
        for prefix, uri in (f.root.nsmap or {}).items():
            if prefix is None:
                merged.setdefault("", uri)
            elif prefix not in merged:
                merged[prefix] = uri
    return merged


# ---------------------------------------------------------------------------
# Convenience entrypoints
# ---------------------------------------------------------------------------


def parse_single(content: bytes, filename: str = "schema.xsd") -> SchemaModel:
    """Parse a single XSD file (no imports / includes resolved)."""
    resolver = ZipResolver(files={})
    parser = XsdParser(
        XsdParseInput(main_filename=filename, main_content=content, resolver=resolver)
    )
    return parser.parse()


def parse_zip(zip_bytes: bytes, main_filename: str | None = None) -> SchemaModel:
    """Parse a ZIP archive containing an XSD plus its referenced files."""
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    if not files:
        raise ValueError("ZIP archive contains no files")
    if main_filename is None:
        xsd_candidates = [n for n in files if n.lower().endswith(".xsd")]
        if not xsd_candidates:
            raise ValueError("ZIP archive contains no .xsd files")
        main_filename = min(xsd_candidates, key=lambda n: (n.count("/"), len(n)))
    if main_filename not in files:
        raise ValueError(f"{main_filename!r} not found in archive")
    resolver = ZipResolver(files=files)
    parser = XsdParser(
        XsdParseInput(
            main_filename=main_filename,
            main_content=files[main_filename],
            resolver=resolver,
        )
    )
    return parser.parse()


def parse_url(url: str) -> SchemaModel:
    """Fetch the main XSD from a URL and resolve references via the same URL chain."""
    fetched = fetch_schema_url(url)
    resolver = ChainedResolver(
        resolvers=[ZipResolver(files={fetched.url: fetched.content}), UrlResolver(base_url=fetched.url)]
    )
    parser = XsdParser(
        XsdParseInput(
            main_filename=fetched.url,
            main_content=fetched.content,
            resolver=resolver,
            allow_url_fallback=True,
            base_url=fetched.url,
        )
    )
    return parser.parse()


def parse_with_url_fallback(
    zip_bytes: bytes | None,
    main_filename: str | None,
    main_bytes: bytes | None,
    base_url: str | None,
) -> SchemaModel:
    """Parse with an in-memory ZIP first and URL fallback for unresolved refs."""
    files: dict[str, bytes] = {}
    if zip_bytes is not None:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            for name in archive.namelist():
                if not name.endswith("/"):
                    files[name] = archive.read(name)
    if main_bytes is not None and main_filename is not None:
        files.setdefault(main_filename, main_bytes)

    if main_filename is None:
        xsd_candidates = [n for n in files if n.lower().endswith(".xsd")]
        if not xsd_candidates:
            raise ValueError("no main XSD identified")
        main_filename = min(xsd_candidates, key=lambda n: (n.count("/"), len(n)))
    if main_filename not in files:
        raise ValueError(f"{main_filename!r} not present")

    zip_resolver = ZipResolver(files=files)
    resolvers: list[SchemaResolver] = [zip_resolver]
    if base_url is not None:
        resolvers.append(UrlResolver(base_url=base_url))
    resolver = ChainedResolver(resolvers=resolvers)

    parser = XsdParser(
        XsdParseInput(
            main_filename=main_filename,
            main_content=files[main_filename],
            resolver=resolver,
            allow_url_fallback=base_url is not None,
            base_url=base_url,
        )
    )
    return parser.parse()
