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

import json
import logging
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.parse import quote

from lxml import etree
from pydantic import BaseModel, Field

from app.config import settings
from app.parser.model import (
    XSD_NS,
    AttributeDecl,
    AttributeGroup,
    ComplexType,
    Diagnostic,
    ElementDecl,
    Group,
    QName,
    SchemaModel,
    SimpleType,
)
from app.parser.security import inspect_dtd, make_parser, only_duplicate_ids
from app.parser.w3c import bytes_for_location
from app.parser.walk import _iter_declarations, iter_elements
from app.parser.xsd_parser import ZipResolver

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


def utf8_bytes(content: str) -> bytes:
    """``content`` as UTF-8, under an XML declaration that says so.

    Source files are kept as decoded text, and pasted text arrives as a
    string. Either one written out as UTF-8 under a declaration that names
    windows-1251 is decoded wrongly by libxml2 ("Invalid bytes in character
    encoding", or silently, for a single-byte encoding like ISO-8859-1).
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
    # "libxml2" (XSD 1.0) or "xmlschema" (XSD 1.1, which also checks assertions,
    # type alternatives and that every IDREF names an ID in the document).
    validator: str = "libxml2"


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
        for head in element.substitution_groups if element.name else ():
            members.setdefault(_local_name(head), []).append(element.name)
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


# The loader's own warnings for imports and includes it could not fetch. The
# same extraction runs in the frontend (SampleXmlDialog), which shows them
# before a sample is even checked.
_UNLOADED_FILE = re.compile(
    r"(?:unresolved (?:import|include|redefine|override) schemaLocation=|could not load )'([^']+)'"
)
# Listing every one of them helps nobody; the first few say what kind of file is missing.
_MAX_LISTED_FILES = 5


def unloaded_files(model: SchemaModel) -> list[str]:
    """Imports and includes the loader could not fetch, as the schema named them."""
    found = (_UNLOADED_FILE.search(d.message) for d in model.diagnostics)
    return list(dict.fromkeys(m.group(1) for m in found if m is not None))


_NAMESPACE_IN_MESSAGE = re.compile(r"\{([^}]+)\}")


def _unloaded_namespace(detail: str, model: SchemaModel) -> str | None:
    """The namespace a reference could not be resolved in, when nothing loaded declares it.

    ``<xs:import namespace="urn:x"/>`` without a schemaLocation leaves nothing to
    resolve and therefore no warning: the only trace is libxml2 refusing the
    reference into it, and "does not resolve to a(n) element declaration" gives
    the user nothing to act on.
    """
    if "resolve" not in detail:
        return None
    declared = {f.target_namespace for f in model.files} | {XSD_NS}
    return next((ns for ns in _NAMESPACE_IN_MESSAGE.findall(detail) if ns not in declared), None)


def _first_error(exc: etree.XMLSchemaParseError, names_by_path: dict[str, str]) -> str | None:
    """libxml2's first complaint, prefixed with the schema file and line it is in."""
    entry = next(iter(exc.error_log), None)  # type: ignore[call-overload]
    if entry is None:
        return None
    filename = (entry.filename or "").removeprefix("file://")
    where = names_by_path.get(filename, filename if filename != "<string>" else "")
    if entry.line:
        where = f"{where} line {entry.line}".strip()
    return f"{where}: {entry.message}" if where else entry.message


def _incomplete(model: SchemaModel, detail: str) -> ValidationSetupError | None:
    """The error for a schema whose imports or includes never loaded, if that is the case."""
    missing = unloaded_files(model)
    namespace = None if missing else _unloaded_namespace(detail, model)
    if not missing and not namespace:
        return None
    if missing:
        listed = ", ".join(missing[:_MAX_LISTED_FILES])
        if len(missing) > _MAX_LISTED_FILES:
            listed += ", …"
        noun = "file" if len(missing) == 1 else "files"
        what = f"{len(missing)} imported or included {noun} did not load ({listed})"
    else:
        what = f"nothing loaded declares the namespace {namespace!r} it imports"
    # "failed to load 'x.xsd'" only repeats what was just said, in temp-dir terms.
    stopped = "" if detail.startswith("failed to load") else f" The compiler stopped at: {detail}"
    return ValidationSetupError(
        f"the schema is incomplete: {what}, so it does not compile. Load the schema "
        f"together with its imported and included files (ZIP upload or URL).{stopped}"
    )


def _compile_failure(
    exc: etree.XMLSchemaParseError, model: SchemaModel, files: _Materialised
) -> ValidationSetupError:
    """Say why the schema does not compile in terms the user can act on.

    libxml2's own wording ("The content is not valid. Expected is (annotation?,
    ...") reads as if the viewer were at fault and never says what to do. The
    causes that actually occur need different answers: files that were never
    loaded (load them), XSD 1.1 when the 1.1 validator is not installed, and a
    schema that really is malformed (fix it, here).
    """
    # libxml2 names the temporary copies; show paths relative to the schema
    # instead, which also keeps the message stable across calls.
    detail = (_first_error(exc, files.names_by_path) or str(exc)).replace(f"{files.root}/", "")
    if files.unavailable:
        detail += f" (unavailable referenced files: {', '.join(files.unavailable)})"
    incomplete = _incomplete(model, detail)
    if incomplete is not None:
        return incomplete
    if model.xsd_version == "1.1":
        return ValidationSetupError(
            "the schema uses XSD 1.1 (xs:assert, xs:alternative, …), and the validator here "
            "is libxml2, which implements XSD 1.0 only — so documents cannot be checked "
            f"against this schema. It stopped at: {detail}"
        )
    return ValidationSetupError(f"the schema itself is not valid XSD: {detail}")


def _location_resolves(location: str | None, path: Path, by_url: dict[str, Path]) -> bool:
    """Whether libxml2 would find ``location`` as written in the file at ``path``."""
    if not location:
        return False
    if "://" in location:
        return _url_key(location) in by_url
    return (path.parent / location).exists()


_REFERENCE_TAGS = tuple(f"{{{XSD_NS}}}{tag}" for tag in ("import", "include", "redefine", "override"))


def _repair_references(
    path: Path,
    data: bytes,
    by_namespace: dict[str, Path],
    by_url: dict[str, Path],
    resolve: Callable[[str], Path | None],
    parser: etree.XMLParser,
) -> bytes | None:
    """Point a reference at the file the loader actually satisfied it with.

    The loader is more forgiving than libxml2, which only ever sees the
    location the schema wrote:

    - an ``<xs:import>`` whose schemaLocation is absent or does not resolve is
      filled from the bundled W3C schemas or from another loaded file of that
      namespace (``app/parser/w3c``, ``xsd_parser._follow_references``). The
      whole namespace was then missing from the compiled schema -- a sample
      rooted in it read "No matching global declaration available for the
      validation root", and a schema that referred to it did not compile at
      all (TiposNFe_v02.xsd + xmldsig);
    - any schemaLocation is also tried as a Windows path (``..\\Base.xsd``),
      percent-decoded, case-insensitively and by bare file name
      (``xsd_parser.ZipResolver``), which read "Failed to load the document …
      for inclusion" here. ``resolve`` is that same lookup.

    Returns the patched bytes, or ``None`` when nothing had to change.
    """
    if not any(tag in data for tag in (b"import", b"include", b"redefine", b"override")):
        return None
    try:
        tree = etree.parse(BytesIO(data), parser)
    except etree.XMLSyntaxError:
        return None  # the compile step reports it, with a better message
    changed = False
    for elem in tree.getroot().iterchildren(*_REFERENCE_TAGS):
        location = (elem.get("schemaLocation") or "").strip()
        if _location_resolves(location, path, by_url):
            continue
        materialised = resolve(location) if location else None
        if materialised is None and elem.tag == _REFERENCE_TAGS[0]:
            materialised = by_namespace.get(elem.get("namespace") or "")
        if materialised is None or materialised == path:
            continue
        # A schemaLocation is a URI: libxml2 refuses one with a raw space in it.
        elem.set("schemaLocation", quote(os.path.relpath(materialised, path.parent)))
        changed = True
    if not changed:
        return None
    # Keep the line numbers a compile error reports: an added attribute stays
    # on its own line, but an added XML declaration would shift every line.
    return etree.tostring(
        tree, xml_declaration=data.lstrip()[:5] == b"<?xml", encoding="UTF-8"
    )


@dataclass
class _Materialised:
    """A schema's source files written to a temporary directory, references repaired."""

    root: Path
    main: Path
    main_has_entities: bool
    by_url: dict[str, Path] = field(default_factory=dict)
    by_namespace: dict[str, Path] = field(default_factory=dict)
    names_by_path: dict[str, str] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)


@contextmanager
def _materialised(model: SchemaModel) -> Iterator[_Materialised]:
    """Write ``model``'s files where a validator can read them, for the length of the block.

    Raises :class:`ValidationSetupError` if the schema has no usable main file.
    """
    main = next((f for f in model.files if f.relationship == "main"), None)
    if main is None:
        raise ValidationSetupError("schema has no main file; cannot validate")
    if main.content is None:
        raise ValidationSetupError("schema source is unavailable; cannot validate")

    with TemporaryDirectory(prefix="xsdval-") as tmp:
        tmp_root = Path(tmp).resolve()
        main_on_disk: Path | None = None
        used_paths: set[PurePosixPath] = set()
        unavailable: list[str] = []
        main_has_entities = False
        by_url: dict[str, Path] = {}
        by_namespace: dict[str, Path] = {}
        written: list[tuple[Path, bytes]] = []
        names_by_path: dict[str, str] = {}
        paths_by_name: dict[str, Path] = {}

        for idx, source in enumerate(model.files):
            if source.content is None:
                unavailable.append(source.filename)
                continue
            data = utf8_bytes(source.content)
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
            names_by_path[str(target)] = source.filename
            paths_by_name.setdefault(source.filename, target)
            if "://" in source.filename:
                by_url.setdefault(_url_key(source.filename), target)
            if source.relationship == "main":
                main_on_disk = target
            elif source.target_namespace:
                by_namespace.setdefault(source.target_namespace, target)

        if main_on_disk is None:  # pragma: no cover - guarded above
            raise ValidationSetupError("schema source is unavailable; cannot validate")

        parser = make_parser(internal_entities=main_has_entities)
        # The loader's own lookup, over the names it loaded the files under.
        loaded_names = ZipResolver(files=dict.fromkeys(paths_by_name, b""))
        # Nothing was loaded that a reference could point at: a single-file schema
        # never needs the repair below, and re-reading it would be wasted work.
        for path, data in written if len(written) > 1 else ():
            name = names_by_path[str(path)]

            def resolve(location: str, name: str = name) -> Path | None:
                found = loaded_names.resolve(name, location)
                return paths_by_name[found[0]] if found else None

            repaired = _repair_references(path, data, by_namespace, by_url, resolve, parser)
            if repaired is not None:
                path.write_bytes(repaired)

        yield _Materialised(
            root=tmp_root,
            main=main_on_disk,
            main_has_entities=main_has_entities,
            by_url=by_url,
            by_namespace=by_namespace,
            names_by_path=names_by_path,
            unavailable=unavailable,
        )


def _too_large(model: SchemaModel) -> ValidationSetupError | None:
    largest = largest_substitution_group(model)
    if largest is None or largest[1] <= MAX_SUBSTITUTION_GROUP:
        return None
    head, members = largest
    return ValidationSetupError(
        f"schema is too large to validate here: the substitution group of {head!r} has "
        f"{members} members (limit {MAX_SUBSTITUTION_GROUP}), and compiling it would "
        "exceed this server's time and memory limits"
    )


def _compile(files: _Materialised) -> etree.XMLSchema:
    """Compile the materialised schema with libxml2 (XSD 1.0)."""

    def read_main(parser: etree.XMLParser) -> etree._ElementTree:
        parser.resolvers.add(_MaterialisedUrlResolver(files.by_url))
        parser.resolvers.add(_BundledW3cResolver())
        return etree.parse(str(files.main), parser)

    parser = make_parser(internal_entities=files.main_has_entities)
    try:
        xsd_tree = read_main(parser)
    except etree.XMLSyntaxError:
        # The loader let a repeated ID through (security.parse_bytes);
        # whether it also breaks the schema is the compiler's call.
        if not only_duplicate_ids(parser):
            raise
        xsd_tree = read_main(make_parser(internal_entities=files.main_has_entities, recover=True))
    return etree.XMLSchema(xsd_tree)


def build_xmlschema(model: SchemaModel) -> etree.XMLSchema:
    """Compile ``model``'s source files into an ``etree.XMLSchema`` (libxml2, XSD 1.0).

    Raises :class:`ValidationSetupError` if the schema has no usable main file,
    is too large for libxml2 to compile within a request, or does not compile.
    """
    too_large = _too_large(model)
    if too_large is not None:
        raise too_large
    with _materialised(model) as files:
        try:
            return _compile(files)
        except etree.XMLSchemaParseError as exc:
            raise _compile_failure(exc, model, files) from exc
        except etree.XMLSyntaxError as exc:
            raise _unparsable(exc, files) from exc


def _unparsable(exc: etree.XMLSyntaxError, files: _Materialised) -> ValidationSetupError:
    detail = str(exc).replace(f"{files.root}/", "")
    return ValidationSetupError(f"cached schema could not be parsed: {detail}")


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


# ---------------------------------------------------------------------------
# XSD 1.1: the xmlschema package, in a worker process
# ---------------------------------------------------------------------------

_WORKER = Path(__file__).with_name("xsd11_worker.py")
# Each worker is a Python process of its own; more than a couple at once would
# take the memory the server itself needs.
_WORKER_SLOTS = threading.BoundedSemaphore(2)


class _Xsd11UnavailableError(Exception):
    """The xmlschema package is not installed."""


class _Xsd11SchemaError(Exception):
    """The schema does not compile as XSD 1.1 either."""


def _worker_request(files: _Materialised) -> dict:
    return {
        "root": str(files.root),
        "main": str(files.main),
        "locations": [[ns, str(path)] for ns, path in files.by_namespace.items()],
        "urls": {url: str(path) for url, path in files.by_url.items()},
        "cpu_seconds": int(settings.xsd11_timeout_seconds) + 1,
        "memory_mb": settings.xsd11_memory_mb,
    }


_CHECK_MAX_CHARS = 2_000_000


class SchemaCheckResponse(BaseModel):
    """What a second reading of the schema itself found (mirrored in schema.ts)."""

    schema_id: str
    # ``not_checked``: the check could not run or finish; ``detail`` says why.
    status: Literal["ok", "findings", "not_checked"]
    # The XSD version the schema was read as.
    version: Literal["1.0", "1.1"]
    findings: list[Diagnostic] = Field(default_factory=list)
    # Findings beyond the ones listed.
    more: int = 0
    detail: str | None = None


def check_schema(model: SchemaModel) -> SchemaCheckResponse:
    """Read the schema with ``xmlschema`` and list the rules of XSD it breaks.

    libxml2, which validates XSD 1.0 documents here, lets a good many invalid
    schemas through (the W3C test suite: restrictions that are none, facets
    that contradict their base, regular expressions XSD does not have).
    ``xmlschema`` reports nearly all of them. It is a second opinion, not a
    gate: the schema stays loaded and usable either way.
    """
    version: Literal["1.0", "1.1"] = "1.1" if model.xsd_version == "1.1" else "1.0"

    def answer(status: str, **fields: object) -> SchemaCheckResponse:
        return SchemaCheckResponse(schema_id=model.schema_id, status=status, version=version, **fields)

    missing = unloaded_files(model)
    if missing:
        # Every reference into a missing file would be reported as undefined.
        return answer("not_checked", detail=f"not all files of the schema are loaded: {missing[0]}")
    size = sum(len(source.content or "") for source in model.files)
    if size > _CHECK_MAX_CHARS:
        # The check runs unasked on every schema loaded, and xmlschema needs
        # ten seconds and several hundred megabytes for one of 8 MB (FundsXML).
        return answer("not_checked", detail="the schema is too large for the automatic check")
    try:
        with _materialised(model) as files:
            if files.unavailable:
                return answer("not_checked", detail="the schema's source is not available")
            request = _worker_request(files) | {"check": version}
            timeout = settings.xsd11_timeout_seconds
            with _WORKER_SLOTS:
                try:
                    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                        [sys.executable, "-I", str(_WORKER)],
                        input=json.dumps(request).encode("utf-8"),
                        capture_output=True,
                        timeout=timeout,
                        env={},
                        cwd=str(files.root),
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    return answer("not_checked", detail=f"the check took longer than {timeout:g} s")
            try:
                reply = json.loads(done.stdout)
            except ValueError:
                logger.warning("schema check worker exited %s", done.returncode)
                return answer("not_checked", detail="the check exceeded this server's limits")
            if reply["status"] != "checked":
                detail = str(reply.get("message") or reply["status"]).replace(f"{files.root}/", "")
                return answer("not_checked", detail=detail[:300])
            ids_by_name = {source.filename: source.id for source in model.files}
            findings = []
            for found in reply["findings"]:
                name = files.names_by_path.get(str(found.get("file") or "").removeprefix("file://"))
                findings.append(
                    Diagnostic(
                        severity="error",
                        message=str(found["message"]).replace(f"{files.root}/", ""),
                        file_id=ids_by_name.get(name) if name else None,
                        line=found.get("line"),
                    )
                )
    except ValidationSetupError as exc:
        return answer("not_checked", detail=str(exc))
    return answer("findings" if findings else "ok", findings=findings, more=int(reply.get("more") or 0))


def _run_worker(files: _Materialised, pretty: bytes) -> list[dict]:
    """Validate ``pretty`` against the materialised schema as XSD 1.1; the raw error records."""
    timeout = settings.xsd11_timeout_seconds
    request = _worker_request(files) | {"xml": pretty.decode("utf-8")}
    with _WORKER_SLOTS:
        try:
            # -I: no user site, no PYTHON* variables, and not the directory the
            # script is in on sys.path. The empty environment keeps the server's
            # secrets out of a process that evaluates the schema author's XPath.
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, "-I", str(_WORKER)],
                input=json.dumps(request).encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env={},
                cwd=str(files.root),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValidationSetupError(
                f"validating against this XSD 1.1 schema took longer than {timeout:g} s and "
                "was stopped; the schema or the document is too large to check here"
            ) from exc
    try:
        reply = json.loads(done.stdout)
    except ValueError as exc:
        # Killed by a limit (CPU, memory) or crashed; stderr says which.
        stderr = done.stderr[-2000:].decode(errors="replace")
        logger.warning("xsd11 worker exited %s: %s", done.returncode, stderr)
        raise ValidationSetupError(
            "validating against this XSD 1.1 schema exceeded this server's time or memory "
            "limits; the schema or the document is too large to check here"
        ) from exc
    if reply["status"] == "unavailable":
        raise _Xsd11UnavailableError(reply["message"])
    if reply["status"] == "validator-error":
        logger.warning("xsd11 validator failed: %s", reply["message"])
        detail = str(reply["message"]).replace(f"{files.root}/", "")
        raise ValidationSetupError(
            "the XSD 1.1 validator failed on this schema and could not check the document "
            f"({detail}); that is a defect of the validator, not a finding about the document"
        )
    if reply["status"] == "schema-error":
        where = files.names_by_path.get(str(reply.get("file") or "").removeprefix("file://"), "")
        if reply.get("line"):
            where = f"{where} line {reply['line']}".strip()
        message = str(reply["message"]).replace(f"{files.root}/", "")
        raise _Xsd11SchemaError(f"{where}: {message}" if where else message)
    return reply["errors"]


_CLARK_RE = re.compile(r"^(?:\{(?P<ns>[^}]*)\})?(?P<local>.+)$")


def _xsd11_errors(records: list[dict], model: SchemaModel) -> list[ValidationErrorItem]:
    items: list[ValidationErrorItem] = []
    for record in records:
        message, path = record["message"], record.get("path")
        ref = None
        declared = _CLARK_RE.match(record.get("declaration") or "")
        if declared:
            ref = find_declaration_by_local(model, declared.group("local"), declared.group("ns"))
        items.append(
            ValidationErrorItem(
                line=record.get("line"),
                message=message,
                type_name=record.get("type_name"),
                domain="xmlschema",
                path=path,
                xsd_ref=ref or _xsd_ref_for_error(model, message, path),
            )
        )
    return items


def _validate_xsd11(
    model: SchemaModel, files: _Materialised, pretty: bytes
) -> ValidationResponse:
    errors = _xsd11_errors(_run_worker(files, pretty), model)
    return ValidationResponse(
        schema_id=model.schema_id,
        is_valid=not errors,
        reformatted_xml=pretty.decode("utf-8"),
        errors=errors,
        validator="xmlschema",
    )


def _not_well_formed(model: SchemaModel, exc: etree.XMLSyntaxError) -> ValidationResponse:
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


def _validate_libxml2(model: SchemaModel, schema: etree.XMLSchema, pretty: bytes) -> ValidationResponse:
    pretty_tree = etree.parse(BytesIO(pretty), make_parser())
    is_valid = bool(schema.validate(pretty_tree))
    return ValidationResponse(
        schema_id=model.schema_id,
        is_valid=is_valid,
        reformatted_xml=pretty.decode("utf-8"),
        errors=[] if is_valid else extract_errors(schema.error_log, model),
    )


def _validator_defect(exc: etree.XMLSchemaValidateError) -> ValidationSetupError:
    return ValidationSetupError(
        f"the XSD 1.0 validator failed on this document and could not check it ({exc}); "
        "that is a defect of the validator, not a finding about the document"
    )


def validate_xml(
    model: SchemaModel, xml_bytes: bytes, *, schema: etree.XMLSchema | None = None
) -> ValidationResponse:
    """Reformat then validate ``xml_bytes`` against ``model``'s schema.

    libxml2 does the work for XSD 1.0. A schema detected as 1.1, and one that
    libxml2 refuses although all its files loaded, goes to the ``xmlschema``
    package instead (:mod:`app.parser.xsd11_worker`): the version detection is
    a heuristic, and a schema whose only 1.1 feature is ``xs:dateTimeStamp``
    looks like 1.0 to it.

    ``schema`` lets a batch caller (tools/sample_audit.py) compile the schema
    once with :func:`build_xmlschema` instead of on every document.
    """
    if schema is not None:
        try:
            return _validate_libxml2(model, schema, pretty_print_and_parse(xml_bytes))
        except etree.XMLSyntaxError as exc:
            return _not_well_formed(model, exc)
        except etree.XMLSchemaValidateError as exc:
            raise _validator_defect(exc) from exc

    with _materialised(model) as files:
        failure: ValidationSetupError | None = None
        if model.xsd_version != "1.1":
            too_large = _too_large(model)
            if too_large is not None:
                raise too_large
            try:
                schema = _compile(files)
            except etree.XMLSchemaParseError as exc:
                failure = _compile_failure(exc, model, files)
                if unloaded_files(model) or files.unavailable:
                    raise failure from exc  # no validator can make up for a missing file
            except etree.XMLSyntaxError as exc:
                raise _unparsable(exc, files) from exc

        try:
            pretty = pretty_print_and_parse(xml_bytes)
        except etree.XMLSyntaxError as exc:
            if failure is not None:
                raise failure from exc
            return _not_well_formed(model, exc)
        defect: ValidationSetupError | None = None
        if schema is not None:
            try:
                return _validate_libxml2(model, schema, pretty)
            except etree.XMLSchemaValidateError as exc:
                # libxml2 gave up half way ("Internal error", on some regular
                # expressions); the other validator may still have an answer.
                defect = _validator_defect(exc)

        if defect is not None:
            try:
                return _validate_xsd11(model, files, pretty)
            except (_Xsd11UnavailableError, _Xsd11SchemaError, ValidationSetupError) as exc:
                raise defect from exc

        try:
            return _validate_xsd11(model, files, pretty)
        except _Xsd11UnavailableError:
            if failure is None:  # detected as 1.1: let libxml2 say where it stops
                try:
                    _compile(files)
                except etree.XMLSchemaParseError as exc:
                    raise _compile_failure(exc, model, files) from exc
                except etree.XMLSyntaxError as exc:
                    raise _unparsable(exc, files) from exc
                raise ValidationSetupError("the XSD 1.1 validator is not installed") from None
            raise failure from None
        except _Xsd11SchemaError as exc:
            if failure is not None:
                # Not a 1.1 schema after all; libxml2's complaint is the familiar one.
                raise failure from exc
            detail = str(exc)
            raise (
                _incomplete(model, detail)
                or ValidationSetupError(f"the schema itself is not valid XSD 1.1: {detail}")
            ) from exc
