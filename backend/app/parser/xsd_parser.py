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
import re
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from functools import partial
from io import BytesIO
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

from lxml import etree

from app.parser import w3c
from app.parser.errors import (
    humanize_syntax_error,
    no_xsd_in_zip_message,
    not_a_schema_message,
)
from app.parser.identity import link_keyrefs
from app.parser.idroles import apply_id_roles
from app.parser.model import (
    XSD_NS,
    Alternative,
    Annotation,
    AppInfo,
    Assertion,
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
    IdentityConstraint,
    IdentityConstraintKind,
    Notation,
    OpenContent,
    OverrideDirective,
    OverrideReplacement,
    Particle,
    RedefineDirective,
    Redefinition,
    SchemaModel,
    SimpleType,
    SourceFile,
    SourceRef,
    VersionConstraints,
    Wildcard,
    XsdVersion,
)
from app.parser.security import (
    FetchedResource,
    SecurityError,
    fetch_schema_url,
    parse_bytes,
)

logger = logging.getLogger(__name__)

XML_NS = "http://www.w3.org/XML/1998/namespace"
VC_NS = "http://www.w3.org/2007/XMLSchema-versioning"


def _xsd(tag: str) -> str:
    return f"{{{XSD_NS}}}{tag}"


_VC_ATTR_MAP: tuple[tuple[str, str], ...] = (
    ("min_version", "minVersion"),
    ("max_version", "maxVersion"),
    ("type_available", "typeAvailable"),
    ("type_unavailable", "typeUnavailable"),
    ("facet_available", "facetAvailable"),
    ("facet_unavailable", "facetUnavailable"),
)


def _vc_attrs(elem: etree._Element) -> VersionConstraints | None:
    """Read the XSD versioning vocabulary (vc:*) attributes off ``elem``.

    vc:* attributes are always namespaced — the prefix may not even be
    declared in the document (unusual but spec-conformant), so we always
    look up by the Clark name ``{VC_NS}local``.
    """
    values: dict[str, str] = {}
    for field_name, local in _VC_ATTR_MAP:
        raw = elem.get(f"{{{VC_NS}}}{local}")
        if raw is not None:
            values[field_name] = raw
    if not values:
        return None
    return VersionConstraints(**values)


# Conditional inclusion is evaluated for the newest version there is: the 1.1
# branch of a schema written for both is the one worth showing, and the one
# the XSD 1.1 validator (app/parser/xsd11_worker.py) takes.
_VC_PROCESSOR_VERSION = Decimal("1.1")
_VC_KNOWN_TYPES: frozenset[str] = frozenset(
    """anyType anySimpleType anyAtomicType string boolean decimal float double duration
    dateTime time date gYearMonth gYear gMonthDay gDay gMonth hexBinary base64Binary anyURI
    QName NOTATION normalizedString token language NMTOKEN NMTOKENS Name NCName ID IDREF
    IDREFS ENTITY ENTITIES integer nonPositiveInteger negativeInteger long int short byte
    nonNegativeInteger unsignedLong unsignedInt unsignedShort unsignedByte positiveInteger
    yearMonthDuration dayTimeDuration dateTimeStamp error""".split()  # noqa: SIM905
)
_VC_KNOWN_FACETS: frozenset[str] = frozenset(
    """length minLength maxLength pattern enumeration whiteSpace maxInclusive maxExclusive
    minInclusive minExclusive totalDigits fractionDigits assertion explicitTimezone""".split()  # noqa: SIM905
)


def _vc_all_known(elem: etree._Element, raw: str, known: frozenset[str]) -> bool:
    """Whether every QName in ``raw`` names a built-in the processor implements."""
    nsmap = elem.nsmap or {}
    for qname in raw.split():
        prefix, sep, local = qname.rpartition(":")
        if (nsmap.get(prefix) if sep else nsmap.get(None)) != XSD_NS or local not in known:
            return False
    return True


def _vc_excluded(elem: etree._Element) -> bool:
    """Whether the vc:* attributes on ``elem`` take it out of the schema (XSD 1.1, 4.2.2)."""

    def version(local: str) -> Decimal | None:
        raw = elem.get(f"{{{VC_NS}}}{local}")
        try:
            return Decimal(raw.strip()) if raw else None
        except InvalidOperation:
            return None  # not a decimal: no condition we can evaluate

    minimum, maximum = version("minVersion"), version("maxVersion")
    if minimum is not None and minimum > _VC_PROCESSOR_VERSION:
        return True
    if maximum is not None and maximum <= _VC_PROCESSOR_VERSION:
        return True
    for local, known, wanted in (
        ("typeAvailable", _VC_KNOWN_TYPES, True),
        ("typeUnavailable", _VC_KNOWN_TYPES, False),
        ("facetAvailable", _VC_KNOWN_FACETS, True),
        ("facetUnavailable", _VC_KNOWN_FACETS, False),
    ):
        raw = elem.get(f"{{{VC_NS}}}{local}")
        if raw is not None and _vc_all_known(elem, raw, known) is not wanted:
            return True
    return False


def _prune_conditional(root: etree._Element) -> list[int]:
    """Remove what vc:* excludes from the tree below ``root``; the lines removed.

    The specification makes this a pre-processing step on the schema document:
    the element and everything in it are gone before anything else looks.
    """
    if not any(VC_NS in name for elem in root.iter() for name in elem.attrib):
        return []
    excluded = [
        elem for elem in root.iterdescendants() if isinstance(elem.tag, str) and _vc_excluded(elem)
    ]
    lines: list[int] = []
    for elem in excluded:
        parent = elem.getparent()
        if parent is None or any(a in excluded for a in elem.iterancestors()):
            continue  # went with an excluded ancestor
        lines.append(elem.sourceline or 0)
        parent.remove(elem)
    return lines


# 1.1-only XSD elements used by the version-detection heuristic. Includes
# both ``xs:assertion`` (simpleType-level) and ``xs:assert`` (complexType-level)
# even though the existing parser already partially recognises ``xs:assertion``
# as a facet kind — both elements only exist in XSD 1.1.
_XSD_1_1_ONLY_TAGS: frozenset[str] = frozenset(
    _xsd(name)
    for name in (
        "assert",
        "assertion",
        "alternative",
        "openContent",
        "defaultOpenContent",
        "override",
        "explicitTimezone",
    )
)


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
    _xsd("explicitTimezone"): "explicitTimezone",
    # ``xs:assertion`` (XSD 1.1) is intentionally omitted — assertions are
    # promoted to ``SimpleType.assertions`` / ``ComplexType.assertions``.
}


# ---------------------------------------------------------------------------
# Schema sources: how to resolve schemaLocation references
# ---------------------------------------------------------------------------


class SchemaResolver:
    """Resolve a schema location (relative or absolute) to XML bytes."""

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        raise NotImplementedError


def _location_spellings(location: str) -> list[str]:
    """``location`` as written, then read as a Windows path and percent-decoded.

    Schemas authored on Windows say ``..\\Base.xsd``, and a schemaLocation is
    a URI, so ``My%20Types.xsd`` names the file ``My Types.xsd``.
    """
    slashed = location.replace("\\", "/")
    return list(dict.fromkeys((location, slashed, unquote(location), unquote(slashed))))


@dataclass
class ZipResolver(SchemaResolver):
    """Resolves locations against a ZIP archive of uploaded files."""

    files: dict[str, bytes]

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        candidates: list[str] = []
        base_dir = posixpath.dirname(base_location) if base_location else ""
        for spelling in _location_spellings(location):
            if base_dir:
                candidates.append(posixpath.normpath(posixpath.join(base_dir, spelling)))
            candidates.append(posixpath.normpath(spelling))
            candidates.append(spelling)
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
        # Loose files are uploaded without their folders, so ``sub/types.xsd``
        # can only be the top-level ``types.xsd``. Not so inside an archive
        # that kept its folders: there a same-named file elsewhere is another file.
        wanted = {posixpath.basename(candidate).lower() for candidate in candidates} - {""}
        for name in self.files:
            if "/" not in name and name.lower() in wanted:
                return name, self.files[name]
        return None


@dataclass
class UrlResolver(SchemaResolver):
    """Fetches references via HTTP(S), SSRF-hardened."""

    base_url: str | None = None

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        base = base_location or self.base_url
        if not base:
            return None
        # A Windows-authored ``..\\types.xsd`` is a path, not a file name with backslashes.
        absolute = urljoin(base, location.replace("\\", "/"))
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


class W3cResolver(SchemaResolver):
    """Serves the bundled W3C schemas (xml.xsd, xmldsig, xenc, xlink) by file name.

    Sits between the ZIP and URL resolvers: a copy shipped by the user wins,
    but nobody has to wait for (or be throttled by) w3.org.
    """

    def resolve(self, base_location: str | None, location: str) -> tuple[str, bytes] | None:
        return w3c.bytes_for_location(location)


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


def _build_resolver(files: dict[str, bytes], base_url: str | None) -> SchemaResolver:
    """Standard chain: uploaded/fetched files, then bundled W3C schemas, then the network."""
    resolvers: list[SchemaResolver] = [ZipResolver(files=files), W3cResolver()]
    if base_url is not None:
        resolvers.append(UrlResolver(base_url=base_url))
    return ChainedResolver(resolvers=resolvers)


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


# Whitespace (optionally behind a UTF-8 BOM) in front of the XML declaration.
# The spec requires ``<?xml`` at byte 0, and lxml enforces that; real-world
# files on GitHub & co. frequently violate it with a stray leading newline.
_LEADING_WS_BEFORE_DECL_RE = re.compile(rb"\A(?:\xef\xbb\xbf)?\s+(?=<\?xml)")


# A Markdown code fence around the schema — what a chat assistant's answer
# looks like when copied wholesale. The closing fence may be followed by
# nothing but whitespace.
_FENCE_OPEN_RE = re.compile(rb"\A(?:\xef\xbb\xbf)?\s*```[A-Za-z0-9_+-]*[ \t]*\r?\n")
_FENCE_CLOSE_RE = re.compile(rb"\r?\n[ \t]*```\s*\Z")


def _strip_markdown_fence(content: bytes) -> tuple[bytes, bool]:
    """Remove a Markdown code fence around the content; report whether one was found."""
    opening = _FENCE_OPEN_RE.match(content)
    if opening is None:
        return content, False
    return _FENCE_CLOSE_RE.sub(b"", content[opening.end() :]), True


# What the browser's own XML rendering adds when its text is copied: a banner
# above the document and a "-" in front of every collapsible element.
_BROWSER_BANNER_RE = re.compile(
    rb"\A(?:\xef\xbb\xbf)?\s*This XML file does not appear to have any style information "
    rb"associated with it\.\s*The document tree is shown below\.\s*"
)
_MARKED_ROOT_RE = re.compile(rb"\A(?:\xef\xbb\xbf)?\s*(?:<\?xml[^>]*\?>\s*)?-[ \t]*<")
_FOLD_MARKER_RE = re.compile(rb"^([ \t]*)-[ \t]*(?=<)", re.MULTILINE)
_FOLDED_NODE_RE = re.compile(rb"^[ \t]*\+[ \t]*<", re.MULTILINE)


def _strip_browser_view(content: bytes) -> tuple[bytes, bool]:
    """Undo a copy of the browser's rendered XML view; report whether it was one.

    Only when the banner or a marker on the root element says so: a "-" at
    the start of an inner line alone can be text. A "+" marks a node that was
    collapsed when copied — its children are not in the text, so there is
    nothing to restore and the content is left for the parser to refuse.
    """
    banner = _BROWSER_BANNER_RE.match(content)
    body = content[banner.end() :] if banner else content
    if banner is None and _MARKED_ROOT_RE.match(body) is None:
        return content, False
    if _FOLDED_NODE_RE.search(body):
        return content, False
    return _FOLD_MARKER_RE.sub(rb"\1", body), True


def _strip_whitespace_before_xml_declaration(content: bytes) -> tuple[bytes, bool]:
    """Drop whitespace that precedes ``<?xml`` so lxml accepts the document.

    Returns the (possibly unchanged) content and whether anything was
    stripped, so the caller can warn the user about the defect.
    """
    match = _LEADING_WS_BEFORE_DECL_RE.match(content)
    if match is None:
        return content, False
    return content[match.end() :], True


def _text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    text = elem.text or ""
    for child in elem:
        text += etree.tostring(child, encoding="unicode")
        if child.tail:
            text += child.tail
    return text


def _token(elem: etree._Element, name: str, default: str | None = None) -> str | None:
    """An attribute value as ``xs:token`` reads it: trimmed, inner runs collapsed.

    lxml hands attribute values back as written, but every enumerated, QName
    and NCName attribute of XSD collapses whitespace, and schemas with
    ``elementFormDefault="qualified "`` are out there. Not for ``default``,
    ``fixed``, facet ``value`` or XPath attributes, where whitespace is data.
    """
    raw = elem.get(name)
    if raw is None:
        return default
    return " ".join(raw.split())


def _choice[T](elem: etree._Element, name: str, allowed: tuple[str, ...], default: T) -> str | T:
    """An enumerated attribute; anything outside ``allowed`` reads as absent."""
    value = _token(elem, name)
    return value if value in allowed else default


_FORMS = ("qualified", "unqualified")
_ELEMENT_BLOCK = ("extension", "restriction", "substitution")
_COMPLEX_DERIVATIONS = ("extension", "restriction")
_SIMPLE_FINAL = ("restriction", "list", "union", "extension")


def _derivation_set(
    elem: etree._Element, name: str, loaded: _LoadedFile, allowed: tuple[str, ...]
) -> list[str]:
    """``block`` / ``final`` as the derivations it rules out.

    Absent, the file's ``blockDefault`` / ``finalDefault`` applies; ``#all``
    means every derivation the component knows.
    """
    raw = _token(elem, name)
    if raw is None:
        raw = _token(loaded.root, f"{name}Default")
    tokens = (raw or "").split()
    return list(allowed) if "#all" in tokens else [d for d in allowed if d in tokens]
_PROCESS_CONTENTS = ("strict", "lax", "skip")


def _bool_attr(elem: etree._Element, name: str, default: bool = False) -> bool:
    raw = elem.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1")


def _occurs(value: str | None, default: int) -> int | Literal["unbounded"]:
    if value is None:
        return default
    value = value.strip()
    if value == "unbounded":
        return "unbounded"
    try:
        return int(value)
    except ValueError:
        return default


def _min_occurs(value: str | None) -> int:
    """``minOccurs`` has no ``unbounded``; a schema that writes it anyway reads as the default."""
    occurs = _occurs(value, 1)
    return occurs if isinstance(occurs, int) else 1


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
    # Set once vc:* took something out: the attributes that prove the schema
    # is XSD 1.1 may have gone with it.
    conditional: bool = False
    default_open_content: dict[int, OpenContent | None] = field(default_factory=dict)
    # Complex types that extend another, with the element their ``base`` is
    # written on (for its namespace declarations).
    extensions: list[tuple[ComplexType, etree._Element]] = field(default_factory=list)
    # (referring file id, schemaLocation as written) -> id of the file it loaded.
    reference_targets: dict[tuple[str, str], str] = field(default_factory=dict)

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
        file_id = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:12]
        content, fenced = _strip_markdown_fence(content)
        if fenced:
            self.state.diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=(
                        f"{filename}: a Markdown code fence (```) around the content was "
                        "removed. Paste the schema itself, not the code block it came in."
                    ),
                    file_id=file_id,
                    line=1,
                )
            )
        content, browser_copy = _strip_browser_view(content)
        if browser_copy:
            self.state.diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=(
                        f"{filename}: this is a copy of the browser's rendered XML view; its "
                        "banner and fold markers ('-') were removed. 'View page source' "
                        "(Ctrl+U) shows the file itself."
                    ),
                    file_id=file_id,
                    line=1,
                )
            )
        content, stripped = _strip_whitespace_before_xml_declaration(content)
        if stripped:
            self.state.diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=(
                        f"{filename}: leading whitespace before the XML declaration was "
                        "removed. The XML specification requires '<?xml' at the very "
                        "start of the file; strict parsers reject this file as-is."
                    ),
                    file_id=file_id,
                    line=1,
                )
            )
        try:
            tree = parse_bytes(content, filename)
        except SecurityError as exc:
            self.state.diagnostics.append(
                Diagnostic(severity="error", message=str(exc), file_id=None)
            )
            return None
        except etree.XMLSyntaxError as exc:
            self.state.diagnostics.append(
                Diagnostic(
                    severity="error",
                    message=humanize_syntax_error(exc, filename, content),
                    file_id=None,
                )
            )
            return None
        root = tree.getroot()
        if _namespace_and_local(root.tag) != (XSD_NS, "schema"):
            self.state.diagnostics.append(
                Diagnostic(severity="error", message=not_a_schema_message(filename, root.tag))
            )
            return None
        removed = _prune_conditional(root)
        if removed:
            self.state.conditional = True
            noun = "declaration was" if len(removed) == 1 else "declarations were"
            lines = ", ".join(str(line) for line in removed[:10]) + (", …" if len(removed) > 10 else "")
            self.state.diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=(
                        f"{filename}: {len(removed)} {noun} left out by vc:* conditions, "
                        f"evaluated for an XSD 1.1 processor (line {lines})"
                    ),
                    file_id=file_id,
                    line=removed[0] or None,
                )
            )
        target_ns = root.get("targetNamespace") or target_ns_hint
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
                location = (elem.get("schemaLocation") or "").strip() or None
                target_ns = elem.get("namespace") if tag == "import" else loaded.target_ns
                if not location:
                    # <xs:import namespace="…"/> without a location: only the
                    # bundled W3C schemas can satisfy it.
                    bundled = w3c.bytes_for_namespace(target_ns) if tag == "import" else None
                    if bundled is not None:
                        self._load(bundled[0], bundled[1], relationship, target_ns)
                    continue
                try:
                    resolved = self.inp.resolver.resolve(loaded.filename, location)
                except SecurityError as exc:
                    self.state.diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            message=(
                                f"{loaded.filename}: could not load '{location}': {exc}"
                            ),
                            file_id=loaded.file_id,
                            line=elem.sourceline,
                        )
                    )
                    continue
                if resolved is None and tag == "import":
                    resolved = w3c.bytes_for_namespace(target_ns)
                if resolved is None:
                    self.state.diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            message=(
                                f"{loaded.filename}: unresolved {tag} "
                                f"schemaLocation='{location}'"
                            ),
                            file_id=loaded.file_id,
                            line=elem.sourceline,
                        )
                    )
                    continue
                ref_filename, ref_bytes = resolved
                target = self._load(ref_filename, ref_bytes, relationship, target_ns)
                if target is not None:
                    self.state.reference_targets[(loaded.file_id, location)] = target.file_id

    # ---- parsing phase -------------------------------------------------

    def parse(self) -> SchemaModel:
        """Build a :class:`SchemaModel` from the loaded XSD file set.

        XSD-version inference is heuristic, in this order: any vc:*
        attribute anywhere in any loaded file → ``"1.1"``; any 1.1-only
        XSD element (xs:assert, xs:assertion, xs:alternative,
        xs:openContent, xs:defaultOpenContent, xs:override,
        xs:explicitTimezone) → ``"1.1"``; explicit ``version`` attribute
        on the main ``xs:schema`` matching ``^1\\.1`` → ``"1.1"``;
        otherwise ``"1.0"``. The viewer never silently upgrades to 1.1
        when nothing identifies the schema as such.
        """
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
            element_form_default=_choice(main.root, "elementFormDefault", _FORMS, "unqualified"),  # type: ignore[arg-type]
            attribute_form_default=_choice(main.root, "attributeFormDefault", _FORMS, "unqualified"),  # type: ignore[arg-type]
            xsd_version=(
                "1.1" if self.state.conditional else _detect_xsd_version(self.state.files, main)
            ),
            xpath_default_namespace=main.root.get("xpathDefaultNamespace"),
            default_attributes=_token(main.root, "defaultAttributes"),
            default_open_content=self._default_open_content(main),
            annotation=self._collect_annotation(main.root),
            schema_version=_token(main.root, "version"),
        )

        for loaded in self.state.files:
            source = SourceFile(
                id=loaded.file_id,
                filename=loaded.filename,
                target_namespace=loaded.target_ns,
                relationship=loaded.relationship,
                content=_decode_source(loaded.raw_content, loaded.tree),
            )
            model.files.append(source)

            for child in loaded.root:
                if not isinstance(child.tag, str):
                    continue
                self._process_top_level(child, loaded, model)

        self._process_redefines(model)
        self._process_overrides(model)
        self._inherit_open_content(model)
        link_keyrefs(model, self.state.diagnostics)
        apply_id_roles(model)

        model.diagnostics.extend(self.state.diagnostics)
        return model

    # Maps a top-level XSD child name to the SchemaModel list that receives
    # the parsed declaration. Used by the override pass to detect which
    # entry was just appended (so it can record the replacement_id).
    _TOP_LEVEL_LIST_ATTR: dict[str, str] = {
        "element": "elements",
        "attribute": "attributes",
        "simpleType": "simple_types",
        "complexType": "complex_types",
        "group": "groups",
        "attributeGroup": "attribute_groups",
        "notation": "notations",
    }

    _REDEFINABLE: frozenset[str] = frozenset(
        {"simpleType", "complexType", "group", "attributeGroup"}
    )

    def _process_redefines(self, model: SchemaModel) -> None:
        """Apply every ``xs:redefine`` block found in any loaded file.

        The redefinition takes the component's id and name; the definition it
        replaces is renamed (see :class:`Redefinition`), and stays reachable as
        the redefinition's base. Files are taken in reverse load order so a
        redefinition that is itself redefined further up is in place first.
        """
        for loaded in reversed(self.state.files):
            for redefine_elem in loaded.root.findall(_xsd("redefine")):
                location = (redefine_elem.get("schemaLocation") or "").strip()
                directive = RedefineDirective(
                    target_file_id=self.state.reference_targets.get(
                        (loaded.file_id, location)
                    ),
                    source_ref=SourceRef(
                        file_id=loaded.file_id, line=redefine_elem.sourceline
                    ),
                )
                for child in redefine_elem:
                    if not isinstance(child.tag, str):
                        continue
                    ns, local = _namespace_and_local(child.tag)
                    name = _token(child, "name")
                    if ns != XSD_NS or local not in self._REDEFINABLE or not name:
                        continue  # annotation
                    target_list = getattr(model, self._TOP_LEVEL_LIST_ATTR[local])
                    qname = self._compose_qname(loaded, name)
                    canonical_id = self._make_id(local, qname)
                    original = next((d for d in target_list if d.id == canonical_id), None)
                    if original is not None:
                        taken = {d.id for d in target_list}
                        suffix = 1
                        while True:
                            original_name = f"{name}~original{suffix if suffix > 1 else ''}"
                            original_id = self._make_id(
                                local, self._compose_qname(loaded, original_name)
                            )
                            if original_id not in taken:
                                break
                            suffix += 1
                        original.name = original_name
                        original.id = original_id
                    else:
                        self.state.diagnostics.append(
                            Diagnostic(
                                severity="warning",
                                message=(
                                    f"{loaded.filename}: xs:redefine of {local} '{name}', "
                                    f"which '{location}' does not define"
                                ),
                                file_id=loaded.file_id,
                                line=child.sourceline,
                            )
                        )
                    self._process_top_level(child, loaded, model)
                    redefinition = target_list[-1]
                    if original is not None:
                        self._point_at_original(
                            redefinition,
                            partial(
                                self._retarget,
                                kind=local,
                                name=name,
                                original_name=original_name,
                                canonical_id=canonical_id,
                                scope=child,
                            ),
                        )
                    directive.redefinitions.append(
                        Redefinition(
                            kind=local,  # type: ignore[arg-type]
                            qname=qname,
                            redefinition_id=redefinition.id,
                            original_id=original.id if original is not None else None,
                            source_ref=SourceRef(
                                file_id=loaded.file_id, line=child.sourceline
                            ),
                        )
                    )
                model.redefines.append(directive)

    def _retarget(
        self,
        ref: str | None,
        *,
        kind: str,
        name: str,
        original_name: str,
        canonical_id: str,
        scope: etree._Element,
    ) -> str | None:
        """``ref`` with the original's name, if it names the redefined component itself."""
        if not ref:
            return ref
        prefix, sep, ref_local = ref.rpartition(":")
        if ref_local != name:
            return ref
        # A chameleon redefine resolves to no namespace at all.
        if self._resolve_ref_id(kind, scope, ref) not in (canonical_id, f"{kind}:{name}"):
            return ref
        return f"{prefix}{sep}{original_name}"

    @staticmethod
    def _point_at_original(
        redefinition: SimpleType | ComplexType | Group | AttributeGroup,
        retarget: Callable[[str | None], str | None],
    ) -> None:
        """Rewrite a redefinition's reference to itself: a type's ``base``, a
        group's ``ref`` to itself among its own particles, an attribute group's
        ``ref`` to itself. References further inside (a child element of the
        redefined type) mean the redefinition and are left alone."""
        if isinstance(redefinition, ComplexType):
            redefinition.base = retarget(redefinition.base)
            redefinition.simple_content_base = retarget(redefinition.simple_content_base)
        elif isinstance(redefinition, SimpleType):
            redefinition.base = retarget(redefinition.base)
        elif isinstance(redefinition, AttributeGroup):
            redefinition.attribute_group_refs = [
                retarget(ref) or ref for ref in redefinition.attribute_group_refs
            ]
        else:
            pending = [redefinition.particle] if redefinition.particle else []
            while pending:
                particle = pending.pop()
                particle.group_ref = retarget(particle.group_ref)
                pending.extend(particle.children)

    def _process_overrides(self, model: SchemaModel) -> None:
        """Apply every ``xs:override`` block found in any loaded file.

        A component in the block replaces the one of the same kind and name
        that another file defines: the original leaves the model (its source
        stays in the Text view, and ``OverrideReplacement.original_source_ref``
        points there). A component that replaces nothing is not part of the
        schema — unlike ``xs:redefine``, an override cannot add — so it is
        left out and reported. Files are taken in reverse load order, so that
        of two overrides of one component the outer one wins.

        An override is a transformation of the overridden document: the
        replacement is read as if written there, under that file's target
        namespace and schema defaults (``defaultAttributes``, ``blockDefault``,
        ``xs:defaultOpenContent``). Its source lines are the block's own.
        """
        by_file_id = {f.file_id: f for f in self.state.files}
        for loaded in reversed(self.state.files):
            for override_elem in loaded.root.findall(_xsd("override")):
                location = (override_elem.get("schemaLocation") or "").strip()
                target_file_id = self.state.reference_targets.get((loaded.file_id, location))
                target = by_file_id.get(target_file_id or "")
                if target is None:
                    continue  # did not load; _follow_references said so
                context = replace(
                    loaded, tree=target.tree, target_ns=target.target_ns or loaded.target_ns
                )

                directive = OverrideDirective(
                    target_file_id=target_file_id,
                    source_ref=SourceRef(
                        file_id=loaded.file_id, line=override_elem.sourceline
                    ),
                )
                for child in override_elem:
                    if not isinstance(child.tag, str):
                        continue
                    ns, local = _namespace_and_local(child.tag)
                    list_attr = self._TOP_LEVEL_LIST_ATTR.get(local)
                    name = _token(child, "name")
                    if ns != XSD_NS or list_attr is None or not name:
                        continue  # annotation
                    target_list = getattr(model, list_attr)
                    qname = self._compose_qname(context, name)
                    canonical_id = self._make_id(local, qname)
                    original = next(
                        (
                            d
                            for d in target_list
                            if d.id == canonical_id
                            and (d.source_ref is None or d.source_ref.file_id != loaded.file_id)
                        ),
                        None,
                    )
                    if original is None:
                        self.state.diagnostics.append(
                            Diagnostic(
                                severity="warning",
                                message=(
                                    f"{loaded.filename}: xs:override of {local} '{name}', which "
                                    f"'{location}' does not define; an override cannot add a "
                                    "component, so it is ignored"
                                ),
                                file_id=loaded.file_id,
                                line=child.sourceline,
                            )
                        )
                        continue
                    position = next(i for i, d in enumerate(target_list) if d is original)
                    self._process_top_level(child, context, model)
                    # In the original's place, so the order of the tree stays the file's.
                    target_list[position] = target_list.pop()
                    directive.replacements.append(
                        OverrideReplacement(
                            kind=local,  # type: ignore[arg-type]
                            qname=qname,
                            replacement_id=canonical_id,
                            source_ref=SourceRef(file_id=loaded.file_id, line=child.sourceline),
                            original_source_ref=original.source_ref,
                        )
                    )
                model.overrides.append(directive)

    def _inherit_open_content(self, model: SchemaModel) -> None:
        """Give a type that extends another its base's open content, unless it has its own.

        An extension keeps the base's content type, open content included; a
        restriction states its content anew, so nothing carries over there.
        """
        by_id = {ct.id: ct for ct in model.complex_types}
        bases = {
            id(ct): self._resolve_ref_id("complexType", scope, ct.base)
            for ct, scope in self.state.extensions
        }

        def effective(ct: ComplexType, seen: frozenset[int]) -> OpenContent | None:
            if ct.open_content is not None or id(ct) in seen:
                return ct.open_content
            base = by_id.get(bases.get(id(ct)) or "")
            inherited = effective(base, seen | {id(ct)}) if base is not None else None
            if inherited is not None and inherited.mode != "none":
                ct.open_content = inherited.model_copy(update={"origin": "base"})
            return ct.open_content

        for ct, _scope in self.state.extensions:
            effective(ct, frozenset())

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
        elif local == "notation":
            name = _token(elem, "name") or ""
            qname = self._compose_qname(loaded, name)
            model.notations.append(
                Notation(
                    id=self._make_id("notation", qname),
                    name=name,
                    qname=qname,
                    public=elem.get("public"),
                    system=elem.get("system"),
                    annotation=self._collect_annotation(elem),
                    source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
                )
            )
        # include/import/redefine/override/annotation — skip here:
        # references were followed in _follow_references, redefine and override
        # blocks get their own pass (_process_redefines/_overrides); top-level annotation
        # is attached to the schema node but we omit it from the model for now.

    # ---- per-construct parsers ----------------------------------------

    def _parse_element(
        self,
        elem: etree._Element,
        loaded: _LoadedFile,
        *,
        is_global: bool,
    ) -> ElementDecl:
        name = _token(elem, "name")
        ref = _token(elem, "ref")
        type_name = _token(elem, "type")
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

        alternatives: list[Alternative] = []
        for alt_elem in elem.findall(_xsd("alternative")):
            alternatives.append(self._parse_alternative(alt_elem, loaded))

        identity_constraints = self._parse_identity_constraints(elem, loaded)
        substitution_groups = (_token(elem, "substitutionGroup") or "").split()

        qname = self._compose_qname(loaded, name) if name and is_global else None
        identifier = self._make_id("element", qname or ref or f"anon-{self.state.next_anon()}")

        return ElementDecl(
            id=identifier,
            name=name,
            qname=qname,
            ref=ref,
            ref_id=self._resolve_ref_id("element", elem, ref),
            type_name=type_name,
            type_inline_simple=type_inline_simple,
            type_inline_complex=type_inline_complex,
            min_occurs=_min_occurs(elem.get("minOccurs")) if not is_global else 1,
            max_occurs=_occurs(elem.get("maxOccurs"), 1) if not is_global else 1,
            default=elem.get("default"),
            fixed=elem.get("fixed"),
            nillable=_bool_attr(elem, "nillable"),
            abstract=_bool_attr(elem, "abstract"),
            substitution_group=substitution_groups[0] if substitution_groups else None,
            substitution_groups=substitution_groups,
            block=_derivation_set(elem, "block", loaded, _ELEMENT_BLOCK),
            final=_derivation_set(elem, "final", loaded, _COMPLEX_DERIVATIONS) if is_global else [],
            form=_choice(elem, "form", _FORMS, None),  # type: ignore[arg-type]
            target_namespace=loaded.target_ns if is_global else _token(elem, "targetNamespace"),
            is_global=is_global,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
            alternatives=alternatives,
            identity_constraints=identity_constraints,
        )

    _IDENTITY_CONSTRAINT_TAGS: frozenset[str] = frozenset({"key", "keyref", "unique"})

    def _parse_identity_constraints(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> list[IdentityConstraint]:
        """Parse ``xs:key`` / ``xs:keyref`` / ``xs:unique`` children of an
        element declaration.

        Identity-constraint names live in the schema's target-namespace
        symbol space regardless of how deeply the owning element is nested
        (unlike local elements/attributes), so ids/qnames are always built
        via ``_compose_qname``/``_make_id`` — the same helpers global
        declarations use. ``refer_id`` (keyref only) is left ``None`` here;
        ``identity.link_keyrefs`` resolves it once every element in the
        model has been parsed.
        """
        constraints: list[IdentityConstraint] = []
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            _, local = _namespace_and_local(child.tag)
            if local not in self._IDENTITY_CONSTRAINT_TAGS:
                continue
            kind: IdentityConstraintKind = local  # type: ignore[assignment]
            name = _token(child, "name")
            ref = _token(child, "ref")  # XSD 1.1 identity-constraint sharing
            if not name and ref:
                name = ref.rpartition(":")[2]
            name = name or ""
            selector_elem = child.find(_xsd("selector"))
            selector = selector_elem.get("xpath", "") if selector_elem is not None else ""
            fields = [f.get("xpath", "") for f in child.findall(_xsd("field"))]
            refer = _token(child, "refer")
            qname = self._compose_qname(loaded, name)
            identifier = self._make_id("identityConstraint", qname)
            constraints.append(
                IdentityConstraint(
                    id=identifier,
                    kind=kind,
                    name=name,
                    qname=qname,
                    selector=selector,
                    fields=fields,
                    refer=refer,
                    refer_id=(
                        self._resolve_ref_id("identityConstraint", child, refer)
                        if refer
                        else None
                    ),
                    xpath_default_namespace=(
                        selector_elem.get("xpathDefaultNamespace")
                        if selector_elem is not None
                        else None
                    ),
                    annotation=self._collect_annotation(child),
                    source_ref=SourceRef(file_id=loaded.file_id, line=child.sourceline),
                    version_constraints=_vc_attrs(child),
                )
            )
        return constraints

    def _parse_alternative(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Alternative:
        """Parse an ``xs:alternative`` (XSD 1.1 conditional type assignment).

        ``test`` is taken verbatim — the same XML attribute-value
        normalisation caveat as ``xs:assert`` applies. ``test`` may be
        absent for the *default* branch, which is selected when no other
        alternative matches.
        """
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
        return Alternative(
            test=elem.get("test"),
            type_name=_token(elem, "type"),
            type_inline_simple=type_inline_simple,
            type_inline_complex=type_inline_complex,
            xpath_default_namespace=elem.get("xpathDefaultNamespace"),
            annotation=self._collect_annotation(elem),
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
        )

    def _parse_attribute(
        self,
        elem: etree._Element,
        loaded: _LoadedFile,
        *,
        is_global: bool,
    ) -> AttributeDecl:
        name = _token(elem, "name")
        ref = _token(elem, "ref")
        type_name = _token(elem, "type")
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

        use = _token(elem, "use", "optional")
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
            form=_choice(elem, "form", _FORMS, None),  # type: ignore[arg-type]
            target_namespace=loaded.target_ns if is_global else _token(elem, "targetNamespace"),
            is_global=is_global,
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
            inheritable=_bool_attr(elem, "inheritable"),
        )

    def _parse_simple_type(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> SimpleType:
        name = _token(elem, "name")
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
        assertions: list[Assertion] = []
        item_type: str | None = None
        item_inline: SimpleType | None = None
        member_types: list[str] = []
        member_inline: list[SimpleType] = []

        if restriction is not None:
            derivation = "restriction"
            base = _token(restriction, "base")
            inline_base = restriction.find(_xsd("simpleType"))
            if inline_base is not None and base is None:
                member_inline.append(self._parse_simple_type(inline_base, loaded))
            facets = self._parse_facets(restriction)
            for assertion_elem in restriction.findall(_xsd("assertion")):
                assertions.append(self._parse_assertion(assertion_elem, loaded))
        elif list_elem is not None:
            derivation = "list"
            item_type = _token(list_elem, "itemType")
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
            assertions=assertions,
            item_type=item_type,
            item_inline=item_inline,
            member_types=member_types,
            member_inline=member_inline,
            final=[] if anonymous else _derivation_set(elem, "final", loaded, _SIMPLE_FINAL),
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
        )

    def _parse_complex_type(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> ComplexType:
        name = _token(elem, "name")
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
        simple_content_inline: SimpleType | None = None
        assertions: list[Assertion] = []
        open_content: OpenContent | None = None
        any_attribute: Wildcard | None = None

        simple_content = elem.find(_xsd("simpleContent"))
        complex_content = elem.find(_xsd("complexContent"))

        # ``xs:assert`` and ``xs:openContent`` sit at the end of the type
        # definition (after the model group and attribute uses) inside
        # whichever derivation wrapper applies. Collect from the appropriate
        # parent: ``inner`` for content-derived types, ``elem`` itself for
        # the implicit-content case.
        assert_parent: etree._Element

        if simple_content is not None:
            content_kind = "simple"
            restr = simple_content.find(_xsd("restriction"))
            ext = simple_content.find(_xsd("extension"))
            inner = restr if restr is not None else ext
            if inner is not None:
                derivation = "restriction" if restr is not None else "extension"
                base = _token(inner, "base")
                simple_content_base = base
                if restr is not None:
                    simple_content_facets = self._parse_facets(restr)
                    inline_content = restr.find(_xsd("simpleType"))
                    if inline_content is not None:
                        simple_content_inline = self._parse_simple_type(inline_content, loaded)
                    # The value assertions among the facets (XSD 1.1).
                    for assertion_elem in restr.findall(_xsd("assertion")):
                        assertions.append(self._parse_assertion(assertion_elem, loaded))
                attrs, groups = self._parse_attribute_children(inner, loaded)
                attributes.extend(attrs)
                attribute_group_refs.extend(groups)
                any_attribute = self._parse_any_attribute(inner)
                assert_parent = inner
            else:
                assert_parent = simple_content
        elif complex_content is not None:
            # ``mixed`` on xs:complexContent overrides the one on xs:complexType.
            mixed = _bool_attr(complex_content, "mixed", default=mixed)
            content_kind = "mixed" if mixed else "complex"
            restr = complex_content.find(_xsd("restriction"))
            ext = complex_content.find(_xsd("extension"))
            inner = restr if restr is not None else ext
            if inner is not None:
                derivation = "restriction" if restr is not None else "extension"
                base = _token(inner, "base")
                particle = self._parse_content_model(inner, loaded)
                attrs, groups = self._parse_attribute_children(inner, loaded)
                attributes.extend(attrs)
                attribute_group_refs.extend(groups)
                any_attribute = self._parse_any_attribute(inner)
                assert_parent = inner
            else:
                assert_parent = complex_content
        else:
            particle = self._parse_content_model(elem, loaded)
            if particle is not None:
                content_kind = "mixed" if mixed else "complex"
            attrs, groups = self._parse_attribute_children(elem, loaded)
            attributes.extend(attrs)
            attribute_group_refs.extend(groups)
            any_attribute = self._parse_any_attribute(elem)
            assert_parent = elem

        for assertion_elem in assert_parent.findall(_xsd("assert")):
            assertions.append(self._parse_assertion(assertion_elem, loaded))

        # ``xs:openContent`` is the first child of the type definition's
        # body (sibling to the model group) per the 1.1 spec; we look it up
        # at the same parent as assertions for consistency.
        open_content_elem = assert_parent.find(_xsd("openContent"))
        if open_content_elem is not None:
            open_content = self._parse_open_content(open_content_elem, loaded)
        elif content_kind != "simple":
            # The file's own default, which reaches an empty content model
            # only when it says so.
            default = self._default_open_content(loaded)
            if default is not None and default.mode != "none" and (
                content_kind != "empty" or default.applies_to_empty
            ):
                open_content = default.model_copy(update={"origin": "default"})

        apply_defaults = _bool_attr(elem, "defaultAttributesApply", default=True)
        complex_type = ComplexType(
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
            any_attribute=any_attribute,
            simple_content_base=simple_content_base,
            simple_content_facets=simple_content_facets,
            simple_content_inline=simple_content_inline,
            assertions=assertions,
            block=[] if anonymous else _derivation_set(elem, "block", loaded, _COMPLEX_DERIVATIONS),
            final=[] if anonymous else _derivation_set(elem, "final", loaded, _COMPLEX_DERIVATIONS),
            open_content=open_content,
            default_attributes_apply=apply_defaults,
            default_attributes=(
                _token(loaded.root, "defaultAttributes") if apply_defaults else None
            ),
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
        )
        if open_content is None and derivation == "extension" and complex_content is not None:
            self.state.extensions.append((complex_type, inner))
        return complex_type

    def _parse_group(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Group:
        name = _token(elem, "name")
        ref = _token(elem, "ref")
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
            version_constraints=_vc_attrs(elem),
        )

    def _parse_attribute_group(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> AttributeGroup:
        name = _token(elem, "name")
        ref = _token(elem, "ref")
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
            any_attribute=self._parse_any_attribute(elem),
            annotation=annotation,
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
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
            min_occurs=_min_occurs(elem.get("minOccurs")),  # type: ignore[arg-type]
            max_occurs=_occurs(elem.get("maxOccurs"), 1),
            annotation=self._collect_annotation(elem),
            version_constraints=_vc_attrs(elem),
        )
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            _, child_local = _namespace_and_local(child.tag)
            if child_local == "element":
                inner = Particle(
                    kind="element",
                    min_occurs=_min_occurs(child.get("minOccurs")),  # type: ignore[arg-type]
                    max_occurs=_occurs(child.get("maxOccurs"), 1),
                    element=self._parse_element(child, loaded, is_global=False),
                    version_constraints=_vc_attrs(child),
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
                        min_occurs=_min_occurs(child.get("minOccurs")),  # type: ignore[arg-type]
                        max_occurs=_occurs(child.get("maxOccurs"), 1),
                        wildcard_namespace=child.get("namespace"),
                        wildcard_process_contents=_choice(child, "processContents", _PROCESS_CONTENTS, None),  # type: ignore[arg-type]
                        wildcard_not_namespace=child.get("notNamespace"),
                        wildcard_not_qname=child.get("notQName"),
                        annotation=self._collect_annotation(child),
                        version_constraints=_vc_attrs(child),
                    )
                )
        return particle

    def _parse_group_ref_particle(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Particle:
        ref = _token(elem, "ref")
        return Particle(
            kind="group-ref",
            min_occurs=_min_occurs(elem.get("minOccurs")),  # type: ignore[arg-type]
            max_occurs=_occurs(elem.get("maxOccurs"), 1),
            group_ref=ref,
            group_inline=(
                None
                if ref is not None
                else self._parse_group(elem, loaded)
            ),
            annotation=self._collect_annotation(elem),
            version_constraints=_vc_attrs(elem),
        )

    def _parse_any_attribute(self, parent: etree._Element) -> Wildcard | None:
        elem = parent.find(_xsd("anyAttribute"))
        return self._parse_wildcard(elem) if elem is not None else None

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
                ref = _token(child, "ref")
                if ref is not None:
                    group_refs.append(ref)
        return attributes, group_refs

    # ---- facets and annotations ---------------------------------------

    def _parse_wildcard(self, elem: etree._Element) -> Wildcard:
        """Parse an ``xs:any`` (or ``xs:anyAttribute``) wildcard.

        XSD 1.1 introduces ``notNamespace`` and ``notQName`` alongside the
        existing ``namespace``; we capture both. Currently used by
        ``_parse_open_content``; the legacy ``Particle.wildcard_*`` fields
        on ``xs:any`` particles remain populated separately for back-compat.
        """
        return Wildcard(
            namespace=elem.get("namespace"),
            not_namespace=elem.get("notNamespace"),
            not_qname=elem.get("notQName"),
            process_contents=_choice(elem, "processContents", _PROCESS_CONTENTS, None),  # type: ignore[arg-type]
            annotation=self._collect_annotation(elem),
        )

    def _default_open_content(self, loaded: _LoadedFile) -> OpenContent | None:
        """The ``xs:defaultOpenContent`` of ``loaded``; it reaches that file's types only."""
        key = id(loaded.tree)  # an override block reads the overridden file's
        if key not in self.state.default_open_content:
            elem = loaded.root.find(_xsd("defaultOpenContent"))
            self.state.default_open_content[key] = (
                None if elem is None else self._parse_open_content(elem, loaded)
            )
        return self.state.default_open_content[key]

    def _parse_open_content(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> OpenContent:
        """Parse ``xs:openContent`` or ``xs:defaultOpenContent`` (XSD 1.1).

        The wildcard child (``xs:any``) is mandatory unless ``mode="none"``;
        we still tolerate its absence for robustness on partial schemas.
        """
        any_elem = elem.find(_xsd("any"))
        wildcard = self._parse_wildcard(any_elem) if any_elem is not None else None
        mode_raw = _token(elem, "mode", "interleave")
        mode = mode_raw if mode_raw in ("interleave", "suffix", "none") else "interleave"
        return OpenContent(
            mode=mode,  # type: ignore[arg-type]
            applies_to_empty=_bool_attr(elem, "appliesToEmpty"),
            wildcard=wildcard,
            annotation=self._collect_annotation(elem),
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
        )

    def _parse_assertion(
        self, elem: etree._Element, loaded: _LoadedFile
    ) -> Assertion:
        """Build an Assertion from ``xs:assert`` or ``xs:assertion``.

        The ``test`` XPath expression is read verbatim via ``elem.get`` —
        XML attribute-value normalisation (per XML 1.0 §3.3.3) trims
        leading/trailing whitespace and collapses internal runs to single
        spaces because ``@test`` is declared ``xs:string`` in the
        XSD-of-XSD. That's accepted for display.
        """
        return Assertion(
            test=elem.get("test", ""),
            xpath_default_namespace=elem.get("xpathDefaultNamespace"),
            annotation=self._collect_annotation(elem),
            source_ref=SourceRef(file_id=loaded.file_id, line=elem.sourceline),
            version_constraints=_vc_attrs(elem),
        )

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
                    version_constraints=_vc_attrs(child),
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

    def _resolve_ref_id(
        self, kind: str, elem: etree._Element, ref: str | None
    ) -> str | None:
        """Turn a ``ref="prefix:Local"`` QName into the id of the global
        declaration it names.

        The prefix is expanded through the namespace declarations in scope at
        ``elem`` (an unprefixed ref uses the default namespace), producing the
        same ``{kind}:{{ns}}Local`` identifier the global declaration got from
        ``_compose_qname``/``_make_id``. Global declarations always live in the
        Returns ``None`` for a prefix no ``xmlns`` declaration covers.
        """
        if not ref:
            return None
        prefix, sep, local = ref.rpartition(":")
        nsmap = elem.nsmap or {}
        uri = nsmap.get(prefix) if sep else nsmap.get(None)
        if sep and uri is None:
            return None
        return f"{kind}:{{{uri}}}{local}" if uri else f"{kind}:{local}"


def _collect_namespaces(files: list[_LoadedFile]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for f in files:
        for prefix, uri in (f.root.nsmap or {}).items():
            if prefix is None:
                merged.setdefault("", uri)
            elif prefix not in merged:
                merged[prefix] = uri
    return merged


def _detect_xsd_version(files: list[_LoadedFile], main: _LoadedFile) -> XsdVersion:
    """Heuristic detection — see ``XsdParser.parse`` for the full rule chain."""
    vc_prefix = f"{{{VC_NS}}}"
    for loaded in files:
        for elem in loaded.root.iter():
            if not isinstance(elem.tag, str):
                continue
            if elem.tag in _XSD_1_1_ONLY_TAGS:
                return "1.1"
            for attr_name in elem.attrib:
                if isinstance(attr_name, str) and attr_name.startswith(vc_prefix):
                    return "1.1"
    explicit = main.root.get("version")
    if explicit and explicit.startswith("1.1"):
        return "1.1"
    return "1.0"


def _decode_source(raw: bytes, tree: etree._ElementTree) -> str:
    """Source text for the Text tab and for validation.

    Decoded with the encoding the parser found (XML declaration or BOM), not
    blindly as UTF-8: a windows-1251 schema otherwise loses every Cyrillic name.
    """
    try:
        return raw.decode(tree.docinfo.encoding or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Convenience entrypoints
# ---------------------------------------------------------------------------


def parse_single(content: bytes, filename: str = "schema.xsd") -> SchemaModel:
    """Parse a single XSD file (no imports / includes resolved)."""
    resolver = _build_resolver({}, None)
    parser = XsdParser(
        XsdParseInput(main_filename=filename, main_content=content, resolver=resolver)
    )
    return parser.parse()


_SCHEMA_LOCATION_RE = re.compile(rb"""schemaLocation\s*=\s*["']([^"']+)["']""")


def _referenced_locations(name: str, content: bytes) -> set[str]:
    """Paths (relative to the archive root) that ``content`` includes/imports."""
    base = posixpath.dirname(name)
    found: set[str] = set()
    for raw in _SCHEMA_LOCATION_RE.findall(content[:512_000]):
        location = raw.decode("utf-8", "replace").strip().replace("\\", "/")
        if not location or "://" in location:
            continue
        found.add(posixpath.normpath(posixpath.join(base, location)))
        found.add(posixpath.basename(location))
    return found


def pick_main_xsd(names: Iterable[str] | Mapping[str, bytes]) -> str | None:
    """Guess the main schema among a set of files.

    With file contents available, prefer an ``.xsd`` that no other file
    includes or imports (the root of the reference graph); ties and the
    names-only case fall back to the shallowest, then shortest path. The
    frontend mirrors this in ``frontend/src/lib/zipEntries.ts`` to
    pre-select the main file — keep the two in step.
    """
    candidates = [n for n in names if n.lower().endswith(".xsd")]
    if not candidates:
        return None
    if isinstance(names, Mapping):
        referenced: set[str] = set()
        for name in candidates:
            referenced |= _referenced_locations(name, names[name])
        roots = [
            n for n in candidates if n not in referenced and posixpath.basename(n) not in referenced
        ]
        if roots:
            candidates = roots
    return min(candidates, key=lambda n: (n.count("/"), len(n)))


def main_not_found_message(main_filename: str, names: Iterable[str]) -> str:
    """Explain that ``main_filename`` matches none of the uploaded files."""
    listed = sorted(n for n in names if n.lower().endswith(".xsd"))
    shown = ", ".join(listed[:8]) + (", …" if len(listed) > 8 else "")
    hint = f" — the upload contains: {shown}" if listed else " — the upload contains no .xsd file"
    return f"main schema {main_filename!r} is not among the uploaded files{hint}"


def parse_zip(zip_bytes: bytes, main_filename: str | None = None) -> SchemaModel:
    """Parse a ZIP archive containing an XSD plus its referenced files."""
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    if not files:
        raise ValueError("ZIP archive contains no files")
    if main_filename is None:
        main_filename = pick_main_xsd(files)
        if main_filename is None:
            raise ValueError(no_xsd_in_zip_message(list(files)))
    if main_filename not in files:
        raise ValueError(main_not_found_message(main_filename, files))
    resolver = _build_resolver(files, None)
    parser = XsdParser(
        XsdParseInput(
            main_filename=main_filename,
            main_content=files[main_filename],
            resolver=resolver,
        )
    )
    return parser.parse()


def parse_files_map(files: dict[str, bytes], main_filename: str) -> SchemaModel:
    """Parse a set of pre-fetched XSD files keyed by filename.

    Used when a caller has already downloaded the main schema and every
    sibling file it imports/includes (e.g. all XSD assets of a GitHub
    release), so the usual ``urljoin`` resolution is skipped in favour of
    filename-based ZIP-style resolution.
    """
    if main_filename not in files:
        raise ValueError(main_not_found_message(main_filename, files))
    resolver = _build_resolver(files, None)
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
    resolver = _build_resolver({fetched.url: fetched.content}, fetched.url)
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
        main_filename = pick_main_xsd(files)
        if main_filename is None:
            raise ValueError(no_xsd_in_zip_message(list(files)))
    if main_filename not in files:
        raise ValueError(main_not_found_message(main_filename, files))

    resolver = _build_resolver(files, base_url)

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
