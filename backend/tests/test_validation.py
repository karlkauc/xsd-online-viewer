"""Validation against a cached schema (app/parser/validation.py)."""

from __future__ import annotations

import time

import pytest

from app.parser import validation
from app.parser.validation import ValidationSetupError, build_xmlschema, validate_xml
from app.parser.xsd_parser import parse_files_map, parse_single

_INVALID = b"""<?xml version="1.0"?>
<Person xmlns="http://example.com/simple"><Nope/></Person>"""


def test_precompiled_schema_gives_the_same_result_without_recompiling(
    simple_xsd_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = parse_single(simple_xsd_bytes, "simple.xsd")
    expected = validate_xml(model, _INVALID)
    schema = build_xmlschema(model)

    def _no_compile(_model):  # noqa: ANN001, ANN202
        raise AssertionError("schema was compiled again")

    monkeypatch.setattr(validation, "build_xmlschema", _no_compile)
    result = validate_xml(model, _INVALID, schema=schema)

    assert not expected.is_valid
    assert result == expected


def test_schema_in_a_legacy_encoding_keeps_its_names() -> None:
    """A windows-1251 schema was decoded as UTF-8, so every Cyrillic name became U+FFFD
    and the duplicates made the schema uncompilable (nalog.gov.ru)."""
    xsd = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<xs:element name="Файл" type="ТипФайла"/>'
        '<xs:complexType name="ТипФайла"><xs:sequence>'
        '<xs:element name="Документ" type="xs:string"/>'
        "</xs:sequence></xs:complexType>"
        '<xs:complexType name="ТипДокумента"><xs:sequence/></xs:complexType>'
        "</xs:schema>"
    ).encode("cp1251")
    model = parse_single(xsd, "nalog.xsd")
    assert "ТипФайла" in (model.files[0].content or "")
    result = validate_xml(model, "<Файл><Документ>x</Документ></Файл>".encode())
    assert result.is_valid, [e.message for e in result.errors]


_ABSOLUTE_IMPORT = {
    "https://example.org/schemas/main.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:b="urn:b" xmlns="urn:m"
           targetNamespace="urn:m" elementFormDefault="qualified">
  <xs:import namespace="urn:b" schemaLocation="https://example.org/base/b.xsd"/>
  <xs:element name="Doc" type="b:BType"/>
</xs:schema>""",
    "https://example.org/base/b.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:b" elementFormDefault="qualified">
  <xs:complexType name="BType"><xs:sequence>
    <xs:element name="X" type="xs:string"/>
  </xs:sequence></xs:complexType>
</xs:schema>""",
}


@pytest.mark.parametrize("referenced_scheme", ["https", "http"])
def test_absolute_schema_location_resolves_to_the_loaded_file(referenced_scheme: str) -> None:
    """Absolute imports were not mapped onto the materialised files (INSPIRE, US-GAAP).

    The http variant is KML: the schema references http://, the fetch followed a
    redirect, and the file is stored under its https:// URL.
    """
    model = parse_files_map(_ABSOLUTE_IMPORT, "https://example.org/schemas/main.xsd")
    assert len(model.files) == 2
    main = next(f for f in model.files if f.relationship == "main")
    main.content = main.content.replace(
        'schemaLocation="https://', f'schemaLocation="{referenced_scheme}://'
    )
    result = validate_xml(model, b'<Doc xmlns="urn:m"><X xmlns="urn:b">x</X></Doc>')
    assert result.is_valid, [e.message for e in result.errors]


def _substitution_schema(members: int) -> bytes:
    names = "".join(
        f'<xs:element name="E{i}" type="xs:string" substitutionGroup="t:item"/>' for i in range(members)
    )
    return (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t" targetNamespace="urn:t">'
        '<xs:element name="item" abstract="true" type="xs:string"/>'
        '<xs:element name="doc"><xs:complexType><xs:choice maxOccurs="unbounded">'
        '<xs:element ref="t:item"/></xs:choice></xs:complexType></xs:element>'
        f"{names}</xs:schema>"
    ).encode()


def test_huge_substitution_group_is_refused_before_compiling() -> None:
    """US-GAAP puts 17 232 items behind one repeated choice; libxml2 then grew by
    ~10 MB/s with no end in sight. Compile time rises ~8x per doubling of the
    group (500: 1 s, 1000: 8 s), far past a 60 s / 512 MiB request."""
    model = parse_single(_substitution_schema(1000), "xbrl.xsd")
    started = time.monotonic()
    with pytest.raises(ValidationSetupError, match="substitution group"):
        build_xmlschema(model)
    assert time.monotonic() - started < 5


def test_small_substitution_group_still_compiles() -> None:
    model = parse_single(_substitution_schema(50), "small.xsd")
    assert build_xmlschema(model) is not None
