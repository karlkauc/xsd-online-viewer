"""User-facing parse-error messages (app/parser/errors.py)."""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from app.parser.errors import (
    describe_binary_format,
    humanize_syntax_error,
    is_binary,
    no_xsd_in_zip_message,
    not_a_schema_message,
)
from app.parser.xsd_parser import parse_single, parse_with_url_fallback


def _syntax_error(data: bytes) -> etree.XMLSyntaxError:
    with pytest.raises(etree.XMLSyntaxError) as info:
        etree.fromstring(data)
    return info.value


def test_known_binary_format_is_named() -> None:
    data = b"PK\x03\x04garbage"
    msg = humanize_syntax_error(_syntax_error(data), "dim.xsd", data)
    assert msg == (
        "dim.xsd: not an XML file — it looks like a ZIP archive "
        "(or a .docx/.xlsx/.odt file), i.e. binary data, not text"
    )


def test_unknown_binary_shows_the_bytes() -> None:
    # A cross-stitch pattern from Pattern Maker: same .xsd extension, no XML.
    data = b"\x10\x05\x80\x03\xb4Q\x08\x00\x04\x00\x00\x00"
    msg = humanize_syntax_error(_syntax_error(data), "uyutnye_tykvy.xsd", data)
    assert msg.startswith("uyutnye_tykvy.xsd: not an XML file — it starts with binary data (b'\\x10\\x05")
    assert msg.endswith("), not text")


def test_plain_text_that_is_not_xml_keeps_the_old_wording() -> None:
    data = b"name;value\n1;2\n"
    msg = humanize_syntax_error(_syntax_error(data), "table.xsd", data)
    assert msg == "table.xsd: not an XML file (it starts with b'name;value\\n1' instead of '<')"


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


def test_binary_sniffing_helpers() -> None:
    assert describe_binary_format(b"%PDF-1.7") == "a PDF document"
    assert describe_binary_format(b"<?xml version") is None
    assert is_binary(b"\x10\x05\x80\x03")
    assert is_binary(b"text\x00more")
    assert not is_binary(b"name;value\r\n")


def test_schema_root_without_namespace_explains_the_missing_xmlns() -> None:
    msg = not_a_schema_message("HU_LABEL_E.xsd", "schema")
    assert msg == (
        "HU_LABEL_E.xsd: the root element <schema> declares no namespace — an XML Schema "
        'must declare xmlns="http://www.w3.org/2001/XMLSchema" (the prefix itself does not '
        "matter, <schema> is as valid as <xs:schema>)"
    )


def test_schema_root_with_obsolete_draft_namespace() -> None:
    msg = not_a_schema_message("old.xsd", "{http://www.w3.org/1999/XMLSchema}schema")
    assert msg == (
        "old.xsd: the root element <schema> uses the obsolete 1999 XML Schema draft namespace "
        "(http://www.w3.org/1999/XMLSchema) — replace it with http://www.w3.org/2001/XMLSchema"
    )
    assert "2000/10" in not_a_schema_message("o.xsd", "{http://www.w3.org/2000/10/XMLSchema}schema")


def test_schema_root_in_a_foreign_namespace() -> None:
    msg = not_a_schema_message("weird.xsd", "{urn:acme}schema")
    assert msg == (
        "weird.xsd: the root element <schema> is in namespace urn:acme, not the XML Schema "
        "namespace http://www.w3.org/2001/XMLSchema"
    )


def test_namespaceless_schema_reaches_the_new_message() -> None:
    with pytest.raises(ValueError, match="declares no namespace"):
        parse_single(b'<schema><element name="a"/></schema>', "HU_LABEL_E.xsd")
