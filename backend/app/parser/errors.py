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


def not_a_schema_message(filename: str, root_tag: object) -> str:
    """Message for a well-formed file whose root is not ``xs:schema``."""
    local = _local_name(root_tag)
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
