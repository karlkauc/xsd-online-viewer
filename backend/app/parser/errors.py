"""Turn parser exceptions into messages a non-expert can act on (no I/O)."""

from __future__ import annotations

import re

from lxml import etree

_LXML_LOCATION_RE = re.compile(r"\s*\(<string>, line \d+\)\s*$")
_XML_NAME_RE = re.compile(r"\{[^}]*\}")


def _local_name(tag: object) -> str:
    return _XML_NAME_RE.sub("", str(tag))


def _sniff_head(content: bytes) -> bytes:
    head = content.lstrip(b"\xef\xbb\xbf \t\r\n")
    return head[:12]


# File types users rename to .xsd, or that simply share the extension. Signatures
# must stay within the 12 bytes _sniff_head keeps.
_BINARY_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "a ZIP archive (or a .docx/.xlsx/.odt file)"),
    (b"%PDF-", "a PDF document"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"\xd0\xcf\x11\xe0", "an old Microsoft Office document (.doc/.xls)"),
    (b"Rar!", "a RAR archive"),
    (b"7z\xbc\xaf\x27\x1c", "a 7-Zip archive"),
    (b"\x89PNG", "a PNG image"),
    (b"\xff\xd8\xff", "a JPEG image"),
    (b"GIF8", "a GIF image"),
)

_TEXT_CONTROL_BYTES = frozenset({0x09, 0x0A, 0x0C, 0x0D, 0x1B})


def describe_binary_format(head: bytes) -> str | None:
    """Name the file type behind a magic-byte prefix, if we recognise it."""
    for signature, description in _BINARY_SIGNATURES:
        if head.startswith(signature):
            return description
    return None


def is_binary(head: bytes) -> bool:
    """True when the bytes cannot be text: a NUL or a stray control byte."""
    return any(byte < 0x20 and byte not in _TEXT_CONTROL_BYTES for byte in head)


def humanize_syntax_error(exc: etree.XMLSyntaxError, filename: str, content: bytes) -> str:
    """Describe a well-formedness failure of ``content`` (the file's bytes).

    A file that does not even start with ``<`` is not XML at all (users have
    uploaded binaries renamed to ``.xsd``); say so instead of quoting lxml's
    "Start tag expected". Binary content is called out separately and named
    where we recognise it, because ".xsd" is also the extension of unrelated
    binary formats (cross-stitch patterns, for one) whose owners have never
    heard of XML Schema. Otherwise keep lxml's message but drop the
    ``(<string>, line N)`` suffix that means nothing to a user.
    """
    head = _sniff_head(content)
    if not head.startswith(b"<"):
        if not head:
            return f"{filename}: the file is empty"
        known = describe_binary_format(head)
        if known:
            return f"{filename}: not an XML file — it looks like {known}, i.e. binary data, not text"
        if is_binary(head):
            return f"{filename}: not an XML file — it starts with binary data ({head!r}), not text"
        return f"{filename}: not an XML file (it starts with {head!r} instead of '<')"
    message = _LXML_LOCATION_RE.sub("", str(exc))
    return f"{filename}: {message}"


XSD_NS = "http://www.w3.org/2001/XMLSchema"

# Namespaces of the pre-Recommendation drafts. Schemas written against them are
# still in circulation, and their root really is a schema — just an old one.
_DRAFT_NAMESPACES: dict[str, str] = {
    "http://www.w3.org/1999/XMLSchema": "the obsolete 1999 XML Schema draft",
    "http://www.w3.org/2000/10/XMLSchema": "the obsolete 2000/10 XML Schema draft",
}


def _namespace_of(tag: str) -> str | None:
    if tag.startswith("{"):
        return tag[1:].partition("}")[0]
    return None


def not_a_schema_message(filename: str, root_tag: object) -> str:
    """Message for a well-formed file whose root is not ``xs:schema``.

    A root named ``schema`` in the wrong (or no) namespace is not an XML
    document that was mistaken for a schema — it *is* a schema, written with a
    missing or outdated ``xmlns``. Saying "not <xs:schema>" there reads as if
    the prefix were the problem, so name the actual namespace instead.
    """
    tag = str(root_tag)
    local = _local_name(tag)
    if local == "schema":
        namespace = _namespace_of(tag)
        if namespace is None:
            return (
                f"{filename}: the root element <schema> declares no namespace — an XML "
                f'Schema must declare xmlns="{XSD_NS}" (the prefix itself does not matter, '
                "<schema> is as valid as <xs:schema>)"
            )
        draft = _DRAFT_NAMESPACES.get(namespace)
        if draft:
            return (
                f"{filename}: the root element <schema> uses {draft} namespace "
                f"({namespace}) — replace it with {XSD_NS}"
            )
        return (
            f"{filename}: the root element <schema> is in namespace {namespace}, "
            f"not the XML Schema namespace {XSD_NS}"
        )
    return (
        f"{filename}: root element is <{local}>, not <xs:schema> — "
        "this looks like an XML document, not an XML Schema"
    )


def no_xsd_in_zip_message(names: list[str]) -> str:
    shown = ", ".join(sorted(names)[:5])
    more = f", … ({len(names)} files)" if len(names) > 5 else ""
    if not names:
        return "ZIP archive contains no files"
    return f"ZIP archive contains no .xsd file (found: {shown}{more})"
