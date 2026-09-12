"""Validate an XML document against a cached XSD schema.

The schema cache only holds each source file's text plus its filename, so to
hand a multi-file schema (include/import/redefine/override) to
``lxml.etree.XMLSchema`` we materialise every file into a temporary directory,
preserving the relative paths that ``schemaLocation`` references rely on. The
submitted XML is pretty-printed first and then validated against the
*reformatted* bytes, so every reported line number indexes the formatted text
the frontend shows back to the user.
"""

from __future__ import annotations

import logging
import os
import re
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from lxml import etree
from pydantic import BaseModel, Field

from app.parser.model import (
    XSD_NS,
    AttributeDecl,
    AttributeGroup,
    ComplexType,
    ElementDecl,
    Group,
    QName,
    SchemaModel,
    SimpleType,
)
from app.parser.security import inspect_dtd, make_parser
from app.parser.w3c import bytes_for_location
from app.parser.walk import _iter_declarations, iter_elements

logger = logging.getLogger(__name__)


class _BundledW3cResolver(etree.Resolver):
    """Let libxml2 load imports of the bundled W3C schemas without network access.

    Only kicks in for locations that do not exist on disk, so a copy the user
    shipped (materialised into the temp dir) still wins.
    """

    def resolve(self, system_url: str | None, public_id: str | None, context):  # noqa: ANN001, ANN201
        if not system_url or Path(system_url).exists():
            return None
        found = bytes_for_location(system_url)
        if found is None:
            return None
        return self.resolve_string(found[1], context)


class _MaterialisedUrlResolver(etree.Resolver):
    """Point absolute ``schemaLocation`` URLs at the files written to the temp dir.

    Files fetched by URL are materialised under their path, but a schema that
    imports ``https://host/x.xsd`` by absolute URL still names the URL, and
    libxml2 must not go to the network for it (INSPIRE, US-GAAP). http and
    https count as the same location: the fetch may have followed a redirect
    from one to the other (KML).
    """

    def __init__(self, files: dict[str, Path]) -> None:
        super().__init__()
        self.files = files

    def resolve(self, system_url: str | None, public_id: str | None, context):  # noqa: ANN001, ANN201
        if not system_url or "://" not in system_url:
            return None
        path = self.files.get(_url_key(system_url))
        return None if path is None else self.resolve_filename(str(path), context)


def _url_key(url: str) -> str:
    """``url`` without scheme, query and fragment."""
    rest = url.split("://", 1)[1]
    return rest.split("#", 1)[0].split("?", 1)[0]


_ENCODING_DECLARATION = re.compile(r"""^(\ufeff?\s*<\?xml[^>]*?\sencoding\s*=\s*)(["'])[^"']*\2""")


def _utf8_bytes(content: str) -> bytes:
    """``content`` as UTF-8, under an XML declaration that says so.

    Source files are kept as decoded text. A windows-1251 schema written back
    as UTF-8 under its original declaration would be decoded wrongly by libxml2.
    """
    return _ENCODING_DECLARATION.sub(r"\1\2UTF-8\2", content, count=1).encode("utf-8")


class ValidationSetupError(ValueError):
    """The cached schema itself cannot be used for validation.

    Distinct from "the submitted XML is invalid": this means the schema has no
    main file, its source is unavailable, or it does not compile as an XSD.
    Surfaced as HTTP 422 by the API layer.
    """


# ---------------------------------------------------------------------------
# Response models (mirrored in frontend/src/types/schema.ts)
# ---------------------------------------------------------------------------


class XsdRef(BaseModel):
    """Best-effort link from a validation error to the schema declaration it
    most likely concerns. ``id`` is the declaration id used everywhere in the
    app, so the frontend can deep-link straight into the Text tab."""

    id: str
    file_id: str
    line: int | None = None
    qname: QName


class ValidationErrorItem(BaseModel):
    line: int | None = None
    column: int | None = None
    message: str
    severity: str = "error"  # "fatal" | "error" | "warning"
    type_name: str | None = None
    domain: str | None = None
    path: str | None = None
    kind: str = "schema-validation"  # "not-well-formed" | "schema-validation"
    xsd_ref: XsdRef | None = None


class ValidationResponse(BaseModel):
    schema_id: str
    is_valid: bool
    # None only when the input is not well-formed (no reformatted text exists).
    reformatted_xml: str | None = None
    errors: list[ValidationErrorItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema reconstruction
# ---------------------------------------------------------------------------


def _safe_relative_path(filename: str, fallback: str) -> PurePosixPath:
    """Map a SourceFile.filename to a temp-dir-relative path, stripping any
    traversal or absolute components. Falls back to ``fallback`` if nothing
    usable remains (e.g. the filename was a bare URL or all ``..``)."""
    # Filenames may be URLs or ZIP-relative paths; normalise separators.
    raw = filename.replace("\\", "/")
    # Drop a URL scheme/host prefix if present (keep only the path part).
    if "://" in raw:
        raw = raw.split("://", 1)[1]
        raw = raw.split("/", 1)[1] if "/" in raw else ""
    parts = [
        seg
        for seg in PurePosixPath(raw).parts
        if seg not in ("", ".", "..", "/") and "\x00" not in seg
    ]
    if not parts:
        return PurePosixPath(fallback)
    return PurePosixPath(*parts)


# libxml2 expands every reference to a substitution-group head into a choice
# over all members. Inside a repeated choice its compile time grows about 8x
# per doubling (500 members: 1 s, 1000: 8 s, 2000: over 60 s) and memory has
# no ceiling: US-GAAP, 17 232 items behind xbrli:item, grew by 10 MB/s. One
# such request would take down a 512 MiB instance, so refuse before compiling.
MAX_SUBSTITUTION_GROUP = 500


def _local_name(qname: str) -> str:
    return qname.rpartition("}")[2].rpartition(":")[2]


def largest_substitution_group(model: SchemaModel) -> tuple[str, int] | None:
    """The biggest substitution group some content model refers to, members counted transitively."""
    members: dict[str, list[str]] = {}
    for element in model.elements:
        if element.name and element.substitution_group:
            members.setdefault(_local_name(element.substitution_group), []).append(element.name)
    if not members:
        return None
    sizes: dict[str, int] = {}

    def size(head: str, seen: frozenset[str]) -> int:
        if head not in sizes:
            sizes[head] = sum(
                1 + (size(name, seen | {name}) if name in members and name not in seen else 0)
                for name in members.get(head, ())
            )
        return sizes[head]

    referenced = {_local_name(e.ref) for e in iter_elements(model) if e.ref} & members.keys()
    return max(
        ((head, size(head, frozenset({head}))) for head in referenced),
        key=lambda head_size: head_size[1],
        default=None,
    )


def _location_resolves(location: str | None, path: Path, by_url: dict[str, Path]) -> bool:
    """Whether libxml2 would find ``location`` as written in the file at ``path``."""
    if not location:
        return False
    if "://" in location:
        return _url_key(location) in by_url
    return (path.parent / location).exists()


def _repair_imports(
    path: Path,
    data: bytes,
    by_namespace: dict[str, Path],
    by_url: dict[str, Path],
    parser: etree.XMLParser,
) -> bytes | None:
    """Point an import at the file the loader actually satisfied it with.

    The loader fills an ``<xs:import>`` whose schemaLocation is absent or does
    not resolve from the bundled W3C schemas or from another loaded file of
    that namespace (``app/parser/w3c``, ``xsd_parser._follow_references``), so
    the model holds a file libxml2 would never load: it only ever sees the
    location the schema wrote. The whole namespace was then missing from the
    compiled schema -- a sample rooted in it read "No matching global
    declaration available for the validation root", and a schema that referred
    to it did not compile at all (TiposNFe_v02.xsd + xmldsig).

    Returns the patched bytes, or ``None`` when nothing had to change.
    """
    if b"import" not in data:
        return None
    try:
        tree = etree.parse(BytesIO(data), parser)
    except etree.XMLSyntaxError:
        return None  # the compile step reports it, with a better message
    changed = False
    for elem in tree.getroot().findall(f"{{{XSD_NS}}}import"):
        materialised = by_namespace.get(elem.get("namespace") or "")
        if materialised is None or materialised == path:
            continue
        if _location_resolves(elem.get("schemaLocation"), path, by_url):
            continue
        elem.set("schemaLocation", os.path.relpath(materialised, path.parent))
        changed = True
    if not changed:
        return None
    # Keep the line numbers a compile error reports: an added attribute stays
    # on its own line, but an added XML declaration would shift every line.
    return etree.tostring(
        tree, xml_declaration=data.lstrip()[:5] == b"<?xml", encoding="UTF-8"
    )


def build_xmlschema(model: SchemaModel) -> etree.XMLSchema:
    """Compile ``model``'s source files into an ``etree.XMLSchema``.

    Raises :class:`ValidationSetupError` if the schema has no usable main file,
    is too large for libxml2 to compile within a request, or does not compile.
    """
    main = next((f for f in model.files if f.relationship == "main"), None)
    if main is None:
        raise ValidationSetupError("schema has no main file; cannot validate")
    if main.content is None:
        raise ValidationSetupError("schema source is unavailable; cannot validate")
    largest = largest_substitution_group(model)
    if largest is not None and largest[1] > MAX_SUBSTITUTION_GROUP:
        head, members = largest
        raise ValidationSetupError(
            f"schema is too large to validate here: the substitution group of {head!r} has "
            f"{members} members (limit {MAX_SUBSTITUTION_GROUP}), and compiling it would "
            "exceed this server's time and memory limits"
        )

    with TemporaryDirectory(prefix="xsdval-") as tmp:
        tmp_root = Path(tmp).resolve()
        main_on_disk: Path | None = None
        used_paths: set[PurePosixPath] = set()
        unavailable: list[str] = []
        main_has_entities = False
        by_url: dict[str, Path] = {}
        by_namespace: dict[str, Path] = {}
        written: list[tuple[Path, bytes]] = []

        for idx, source in enumerate(model.files):
            if source.content is None:
                unavailable.append(source.filename)
                continue
            data = _utf8_bytes(source.content)
            if inspect_dtd(data) and source.relationship == "main":
                main_has_entities = True

            rel = _safe_relative_path(source.filename, f"file-{idx}.xsd")
            if rel in used_paths:
                rel = PurePosixPath(f"{source.id}-{rel.name}")
            used_paths.add(rel)

            target = (tmp_root / rel).resolve()
            if not target.is_relative_to(tmp_root):
                raise ValidationSetupError(
                    f"refusing unsafe schema filename: {source.filename!r}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append((target, data))
            if "://" in source.filename:
                by_url.setdefault(_url_key(source.filename), target)
            if source.relationship == "main":
                main_on_disk = target
            elif source.target_namespace:
                by_namespace.setdefault(source.target_namespace, target)

        if main_on_disk is None:  # pragma: no cover - guarded above
            raise ValidationSetupError("schema source is unavailable; cannot validate")

        parser = make_parser(internal_entities=main_has_entities)
        # Nothing was loaded that an import could point at: a single-file schema
        # never needs the repair below, and re-reading it would be wasted work.
        for path, data in written if by_namespace else ():
            repaired = _repair_imports(path, data, by_namespace, by_url, parser)
            if repaired is not None:
                path.write_bytes(repaired)

        try:
            parser.resolvers.add(_MaterialisedUrlResolver(by_url))
            parser.resolvers.add(_BundledW3cResolver())
            xsd_tree = etree.parse(str(main_on_disk), parser)
            return etree.XMLSchema(xsd_tree)
        except etree.XMLSchemaParseError as exc:
            # libxml2 names the temporary copies; show paths relative to the
            # schema instead, which also keeps the message stable across calls.
            detail = str(exc).replace(f"{tmp_root}/", "")
            if unavailable:
                detail += f" (unavailable referenced files: {', '.join(unavailable)})"
            raise ValidationSetupError(
                f"the loaded schema does not compile: {detail}"
            ) from exc
        except etree.XMLSyntaxError as exc:
            detail = str(exc).replace(f"{tmp_root}/", "")
            raise ValidationSetupError(
                f"cached schema could not be parsed: {detail}"
            ) from exc


# ---------------------------------------------------------------------------
# Reformat + validate
# ---------------------------------------------------------------------------


def pretty_print_and_parse(xml_bytes: bytes) -> bytes:
    """Pretty-print ``xml_bytes``. Raises ``etree.XMLSyntaxError`` if the input
    is not well-formed (handled by the caller as a distinct error class)."""
    inspect_dtd(xml_bytes)
    parser = etree.XMLParser(
        remove_blank_text=True,
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        recover=False,
    )
    tree = etree.parse(BytesIO(xml_bytes), parser)
    return etree.tostring(
        tree, pretty_print=True, encoding="UTF-8", xml_declaration=True
    )


_ELEMENT_RE = re.compile(r"^Element '(?:\{(?P<ns>[^}]*)\})?(?P<local>[^']+)'")
_ATTRIBUTE_RE = re.compile(
    r"attribute '(?:\{(?P<ns>[^}]*)\})?(?P<local>[^']+)'"
)


def _local(qname: QName | None, name: str | None) -> str | None:
    if name:
        return name
    if qname:
        return qname.split(":")[-1]
    return None


def find_declaration_by_local(
    model: SchemaModel, local: str, ns: str | None
) -> XsdRef | None:
    """Best-effort: resolve a local name to a schema declaration. Never raises;
    an unmatched name simply yields ``None``. A namespace-qualified match
    (``ns`` equals the schema's target namespace) wins over a bare local-name
    match."""
    ns_matches = ns is None or ns == "" or ns == model.target_namespace
    fallback: XsdRef | None = None
    for decl in _iter_declarations(model):
        if not isinstance(
            decl,
            (ElementDecl, AttributeDecl, ComplexType, SimpleType, Group, AttributeGroup),
        ):
            continue
        decl_local = _local(getattr(decl, "qname", None), getattr(decl, "name", None))
        if decl_local != local:
            continue
        ref_qname = getattr(decl, "qname", None) or decl_local
        sref = decl.source_ref
        xref = XsdRef(
            id=decl.id,
            file_id=sref.file_id if sref else "",
            line=sref.line if sref else None,
            qname=ref_qname,
        )
        if ns_matches:
            return xref
        if fallback is None:
            fallback = xref
    return fallback


def _xsd_ref_for_error(
    model: SchemaModel, message: str, path: str | None
) -> XsdRef | None:
    for regex in (_ELEMENT_RE, _ATTRIBUTE_RE):
        m = regex.search(message)
        if m:
            ref = find_declaration_by_local(
                model, m.group("local"), m.group("ns")
            )
            if ref is not None:
                return ref
    if path:
        tail = path.rstrip("/").split("/")[-1]
        tail = tail.split(":")[-1].split("[")[0]
        if tail:
            return find_declaration_by_local(model, tail, None)
    return None


_SEVERITY = {"FATAL": "fatal", "ERROR": "error", "WARNING": "warning"}


def extract_errors(
    error_log: object, model: SchemaModel
) -> list[ValidationErrorItem]:
    items: list[ValidationErrorItem] = []
    for entry in error_log:  # type: ignore[attr-defined]
        message = entry.message or ""
        items.append(
            ValidationErrorItem(
                line=entry.line or None,
                column=entry.column or None,
                message=message,
                severity=_SEVERITY.get(entry.level_name or "", "error"),
                type_name=entry.type_name or None,
                domain=entry.domain_name or None,
                path=entry.path or None,
                kind="schema-validation",
                xsd_ref=_xsd_ref_for_error(model, message, entry.path),
            )
        )
    return items


def validate_xml(
    model: SchemaModel, xml_bytes: bytes, *, schema: etree.XMLSchema | None = None
) -> ValidationResponse:
    """Reformat then validate ``xml_bytes`` against ``model``'s schema.

    ``schema`` lets a batch caller (tools/sample_audit.py) compile the schema
    once with :func:`build_xmlschema` instead of on every document.
    """
    if schema is None:
        schema = build_xmlschema(model)

    try:
        pretty = pretty_print_and_parse(xml_bytes)
    except etree.XMLSyntaxError as exc:
        return ValidationResponse(
            schema_id=model.schema_id,
            is_valid=False,
            reformatted_xml=None,
            errors=[
                ValidationErrorItem(
                    line=exc.lineno or None,
                    column=exc.offset or None,
                    message=str(exc.msg or exc),
                    severity="fatal",
                    kind="not-well-formed",
                )
            ],
        )

    pretty_tree = etree.parse(BytesIO(pretty), make_parser())
    is_valid = bool(schema.validate(pretty_tree))
    errors = [] if is_valid else extract_errors(schema.error_log, model)
    return ValidationResponse(
        schema_id=model.schema_id,
        is_valid=is_valid,
        reformatted_xml=pretty.decode("utf-8"),
        errors=errors,
    )
