"""User-facing parse-error messages (app/parser/errors.py)."""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from app.parser.errors import humanize_syntax_error, no_xsd_in_zip_message, not_a_schema_message
from app.parser.xsd_parser import parse_single, parse_with_url_fallback


def _syntax_error(data: bytes) -> etree.XMLSyntaxError:
    with pytest.raises(etree.XMLSyntaxError) as info:
        etree.fromstring(data)
    return info.value


def test_binary_file_is_not_xml() -> None:
    data = b"PK\x03\x04garbage"
    msg = humanize_syntax_error(_syntax_error(data), "dim.xsd", data)
    assert msg.startswith("dim.xsd: not an XML file (it starts with b'PK\\x03\\x04")


def test_empty_file() -> None:
    assert humanize_syntax_error(_syntax_error(b"  "), "e.xsd", b"  ") == "e.xsd: the file is empty"


def test_lxml_location_suffix_stripped() -> None:
    data = b"<a><b></a>"
    msg = humanize_syntax_error(_syntax_error(data), "x.xsd", data)
    assert msg.startswith("x.xsd: Opening and ending tag mismatch")
    assert "<string>" not in msg


def test_not_a_schema_names_root() -> None:
    msg = not_a_schema_message("db.xml", "{urn:x}games")
    assert msg == (
        "db.xml: root element is <games>, not <xs:schema> — "
        "this looks like an XML document, not an XML Schema"
    )


def test_parse_single_surfaces_document_hint() -> None:
    with pytest.raises(ValueError, match="looks like an XML document"):
        parse_single(b"<games><game/></games>", "db.xml")


def test_zip_without_xsd_lists_contents() -> None:
    assert no_xsd_in_zip_message([]) == "ZIP archive contains no files"
    assert no_xsd_in_zip_message(["b.stl", "a.txt"]) == (
        "ZIP archive contains no .xsd file (found: a.txt, b.stl)"
    )
    msg = no_xsd_in_zip_message([f"f{i}.bin" for i in range(7)])
    assert msg.endswith(", … (7 files))")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("model.stl", b"solid")
    with pytest.raises(ValueError, match="contains no .xsd file"):
        parse_with_url_fallback(zip_bytes=buf.getvalue(), main_filename=None, main_bytes=None, base_url=None)
