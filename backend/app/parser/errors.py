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


def humanize_syntax_error(exc: etree.XMLSyntaxError, filename: str, content: bytes) -> str:
    """Describe a well-formedness failure of ``content`` (the file's bytes).

    A file that does not even start with ``<`` is not XML at all (users have
    uploaded binaries renamed to ``.xsd``); say so instead of quoting lxml's
    "Start tag expected". Otherwise keep lxml's message but drop the
    ``(<string>, line N)`` suffix that means nothing to a user.
    """
    head = _sniff_head(content)
    if not head.startswith(b"<"):
        if not head:
            return f"{filename}: the file is empty"
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
