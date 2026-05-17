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
import re
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from lxml import etree
from pydantic import BaseModel, Field

from app.parser.model import (
    AttributeDecl,
    AttributeGroup,
    ComplexType,
    ElementDecl,
    Group,
    Particle,
    QName,
    SchemaModel,
    SimpleType,
)
from app.parser.security import _reject_known_bombs, make_parser

logger = logging.getLogger(__name__)


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


def build_xmlschema(model: SchemaModel) -> etree.XMLSchema:
    """Compile ``model``'s source files into an ``etree.XMLSchema``.

    Raises :class:`ValidationSetupError` if the schema has no usable main file
    or does not compile.
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

        for idx, source in enumerate(model.files):
            if source.content is None:
                unavailable.append(source.filename)
                continue
            data = source.content.encode("utf-8")
            _reject_known_bombs(data)

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
            if source.relationship == "main":
                main_on_disk = target

        if main_on_disk is None:  # pragma: no cover - guarded above
            raise ValidationSetupError("schema source is unavailable; cannot validate")

        try:
            xsd_tree = etree.parse(str(main_on_disk), make_parser())
            return etree.XMLSchema(xsd_tree)
        except etree.XMLSchemaParseError as exc:
            detail = str(exc)
            if unavailable:
                detail += f" (unavailable referenced files: {', '.join(unavailable)})"
            raise ValidationSetupError(
                f"cached schema is not itself a valid XSD: {detail}"
            ) from exc
        except etree.XMLSyntaxError as exc:
            raise ValidationSetupError(
                f"cached schema could not be parsed: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Reformat + validate
# ---------------------------------------------------------------------------


def pretty_print_and_parse(xml_bytes: bytes) -> bytes:
    """Pretty-print ``xml_bytes``. Raises ``etree.XMLSyntaxError`` if the input
    is not well-formed (handled by the caller as a distinct error class)."""
    _reject_known_bombs(xml_bytes)
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


def _iter_particle(particle: Particle | None) -> Iterator[object]:
    if particle is None:
        return
    if particle.element is not None:
        yield from _iter_element(particle.element)
    if particle.group_inline is not None:
        yield from _iter_group(particle.group_inline)
    for child in particle.children:
        yield from _iter_particle(child)


def _iter_element(element: ElementDecl) -> Iterator[object]:
    yield element
    if element.type_inline_complex is not None:
        yield from _iter_complex(element.type_inline_complex)
    if element.type_inline_simple is not None:
        yield element.type_inline_simple


def _iter_complex(ct: ComplexType) -> Iterator[object]:
    yield ct
    yield from _iter_particle(ct.particle)
    yield from ct.attributes


def _iter_group(group: Group) -> Iterator[object]:
    yield group
    yield from _iter_particle(group.particle)


def _iter_declarations(model: SchemaModel) -> Iterator[object]:
    """Yield every named-or-local declaration, including ones nested inside
    complex types / groups, so local elements (e.g. ``<Age>`` inside a content
    model) can still be resolved for the best-effort XSD reference."""
    for element in model.elements:
        yield from _iter_element(element)
    for ct in model.complex_types:
        yield from _iter_complex(ct)
    yield from model.simple_types
    yield from model.attributes
    for group in model.groups:
        yield from _iter_group(group)
    for ag in model.attribute_groups:
        yield ag
        yield from ag.attributes


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


def validate_xml(model: SchemaModel, xml_bytes: bytes) -> ValidationResponse:
    """Reformat then validate ``xml_bytes`` against ``model``'s schema."""
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
