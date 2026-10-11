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


def test_a_schema_that_does_not_compile_says_so_plainly() -> None:
    """Shown in the sample dialog and the Validation tab, so no "cached schema" jargon."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        b'<xs:element name="A" type="Missing"/></xs:schema>',
        "a.xsd",
    )
    with pytest.raises(ValidationSetupError, match="^the schema itself is not valid XSD: "):
        build_xmlschema(model)


def test_a_compile_error_names_files_relative_to_the_schema() -> None:
    """libxml2 reports the temporary copy (/tmp/xsdval-<random>/...), which reads badly
    and gave every occurrence of the same defect a different sample_issue fingerprint."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        b'<xs:include schemaLocation="parts/missing.xsd"/>'
        b'<xs:element name="A" type="xs:string"/></xs:schema>',
        "main.xsd",
    )
    with pytest.raises(ValidationSetupError) as raised:
        build_xmlschema(model)
    message = str(raised.value)
    assert "parts/missing.xsd" in message
    assert "xsdval-" not in message and "/tmp" not in message


_DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
_SIGNATURE = (
    f'<ds:Signature xmlns:ds="{_DSIG_NS}"><ds:SignedInfo>'
    '<ds:CanonicalizationMethod Algorithm="urn:c14n"/>'
    '<ds:SignatureMethod Algorithm="urn:rsa"/>'
    '<ds:Reference><ds:DigestMethod Algorithm="urn:sha"/><ds:DigestValue>AA==</ds:DigestValue>'
    "</ds:Reference></ds:SignedInfo><ds:SignatureValue>AA==</ds:SignatureValue></ds:Signature>"
)


def _bundled_import(location: str) -> bytes:
    return (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:tns="urn:t" '
        'targetNamespace="urn:t" elementFormDefault="qualified">'
        f'<xs:import namespace="{_DSIG_NS}"{location}/>'
        '<xs:element name="Doc" type="xs:string"/>'
        "</xs:schema>"
    ).encode()


@pytest.mark.parametrize(
    "location", ["", ' schemaLocation="xmldsig-core-schema_v01.xsd"'], ids=["none", "stale"]
)
def test_an_element_of_a_bundled_import_can_be_the_validation_root(location: str) -> None:
    """A sample rooted at ds:Signature read "No matching global declaration available
    for the validation root": the parser satisfies such an import from app/parser/w3c,
    but libxml2 was left with the import the schema wrote (TiposNFe_v02.xsd)."""
    model = parse_single(_bundled_import(location), "main.xsd")
    assert [f.filename for f in model.files] == ["main.xsd", "xmldsig-core-schema.xsd"]

    result = validate_xml(model, _SIGNATURE.encode())

    assert result.is_valid, [e.message for e in result.errors]


def test_a_reference_into_a_bundled_import_compiles() -> None:
    """Worse than an unusable root: the whole schema stopped compiling, so neither a
    sample nor the user's own XML could be checked at all."""
    model = parse_single(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:tns="urn:t" '
        f'xmlns:ds="{_DSIG_NS}" targetNamespace="urn:t" elementFormDefault="qualified">'
        f'<xs:import namespace="{_DSIG_NS}"/>'
        '<xs:element name="Doc"><xs:complexType><xs:sequence>'
        '<xs:element ref="ds:Signature"/></xs:sequence></xs:complexType></xs:element>'
        "</xs:schema>".encode(),
        "main.xsd",
    )

    result = validate_xml(model, f'<tns:Doc xmlns:tns="urn:t">{_SIGNATURE}</tns:Doc>'.encode())

    assert result.is_valid, [e.message for e in result.errors]


def test_a_bundled_import_of_an_imported_file_is_repaired_too() -> None:
    """The import may sit in any loaded file, not just the main one."""
    files = {
        "main.xsd": (
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:s="urn:s" '
            b'xmlns:tns="urn:t" targetNamespace="urn:t" elementFormDefault="qualified">'
            b'<xs:import namespace="urn:s" schemaLocation="signed.xsd"/>'
            b'<xs:element name="Doc" type="s:SignedType"/>'
            b"</xs:schema>"
        ),
        "signed.xsd": (
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            f'xmlns:ds="{_DSIG_NS}" targetNamespace="urn:s" elementFormDefault="qualified">'
            f'<xs:import namespace="{_DSIG_NS}"/>'
            '<xs:complexType name="SignedType"><xs:sequence>'
            '<xs:element ref="ds:Signature"/></xs:sequence></xs:complexType>'
            "</xs:schema>"
        ).encode(),
    }
    model = parse_files_map(files, "main.xsd")

    result = validate_xml(model, f'<tns:Doc xmlns:tns="urn:t">{_SIGNATURE}</tns:Doc>'.encode())

    assert result.is_valid, [e.message for e in result.errors]


def test_a_bundled_schema_can_reach_the_bundled_schema_it_imports() -> None:
    """xlink.xsd imports xml.xsd by its w3.org URL, and the loader serves that from
    the bundle as well: the copy libxml2 compiles has to reach it without a network."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        b'xmlns:xl="http://www.w3.org/1999/xlink" xmlns:tns="urn:t" '
        b'targetNamespace="urn:t" elementFormDefault="qualified">'
        b'<xs:import namespace="http://www.w3.org/1999/xlink"/>'
        b'<xs:element name="Link"><xs:complexType>'
        b'<xs:attributeGroup ref="xl:simpleAttrs"/></xs:complexType></xs:element>'
        b"</xs:schema>",
        "main.xsd",
    )
    assert "xml.xsd" in [f.filename for f in model.files]

    result = validate_xml(
        model,
        b'<tns:Link xmlns:tns="urn:t" xmlns:xl="http://www.w3.org/1999/xlink" '
        b'xl:type="simple" xl:href="urn:x"/>',
    )

    assert result.is_valid, [e.message for e in result.errors]


def test_an_incomplete_schema_names_the_files_that_did_not_load() -> None:
    """libxml2's "does not resolve to a(n) element declaration" says nothing a user can
    act on; what they need is which files are missing and how to load them (UBL)."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:cac="urn:cac" '
        b'xmlns:tns="urn:t" targetNamespace="urn:t" elementFormDefault="qualified">'
        b'<xs:import namespace="urn:cac" schemaLocation="common/cac.xsd"/>'
        b'<xs:element name="Invoice"><xs:complexType><xs:sequence>'
        b'<xs:element ref="cac:Party"/></xs:sequence></xs:complexType></xs:element>'
        b"</xs:schema>",
        "invoice.xsd",
    )

    with pytest.raises(ValidationSetupError) as raised:
        build_xmlschema(model)

    message = str(raised.value)
    assert message.startswith("the schema is incomplete: ")
    assert "common/cac.xsd" in message
    assert "ZIP" in message  # how to load the schema completely
    # libxml2's own "failed to load ...: No such file or directory" only repeats that,
    # in terms of the temporary copies, so it is left out.
    assert "No such file" not in message


def test_a_schema_that_is_not_valid_xsd_says_so_with_file_and_line() -> None:
    """A hand-written schema with a misplaced element compiled to a bare libxml2 dump
    ("Element '{...}element': The content is not valid. Expected is (annotation?, ..."),
    which reads as if the viewer were at fault and never says where to look."""
    model = parse_single(
        b'<?xml version="1.0"?>\n'
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        b'  <xs:element name="Zaznamy">\n'
        b'    <xs:sequence>\n'
        b'      <xs:element name="Zaznam" type="xs:string"/>\n'
        b"    </xs:sequence>\n"
        b"  </xs:element>\n"
        b"</xs:schema>",
        "schema.xsd",
    )

    with pytest.raises(ValidationSetupError) as raised:
        build_xmlschema(model)

    message = str(raised.value)
    assert message.startswith("the schema itself is not valid XSD: ")
    assert "schema.xsd" in message and "line 4" in message  # the misplaced xs:sequence
    assert "The content is not valid" in message


def test_an_xsd_11_schema_says_the_validator_only_does_1_0() -> None:
    """XSD 1.1 is the most common reason a schema does not compile here; "does not
    compile" makes a perfectly good 1.1 schema look broken."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        b'<xs:element name="A"><xs:complexType><xs:sequence>'
        b'<xs:element name="B" type="xs:string"/></xs:sequence>'
        b'<xs:assert test="B &gt; 0"/></xs:complexType></xs:element>'
        b"</xs:schema>",
        "assert.xsd",
    )
    assert model.xsd_version == "1.1"

    with pytest.raises(ValidationSetupError) as raised:
        build_xmlschema(model)

    message = str(raised.value)
    assert "XSD 1.1" in message and "1.0" in message
    assert "libxml2" in message


def test_an_import_of_a_namespace_nothing_declares_reads_as_incomplete() -> None:
    """<xs:import namespace="…"/> without a location leaves no "unresolved" warning --
    the only trace is libxml2's "does not resolve", which the user cannot act on."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:cac="urn:cac" '
        b'xmlns:tns="urn:t" targetNamespace="urn:t" elementFormDefault="qualified">'
        b'<xs:import namespace="urn:cac"/>'
        b'<xs:element name="Invoice"><xs:complexType><xs:sequence>'
        b'<xs:element ref="cac:Party"/></xs:sequence></xs:complexType></xs:element>'
        b"</xs:schema>",
        "invoice.xsd",
    )
    assert model.diagnostics == []  # nothing warned: there was no location to resolve

    with pytest.raises(ValidationSetupError) as raised:
        build_xmlschema(model)

    message = str(raised.value)
    assert message.startswith("the schema is incomplete: ")
    assert "urn:cac" in message
    assert "ZIP" in message


def test_a_type_the_schema_itself_never_defines_is_not_called_incomplete() -> None:
    """The counterpart: a name that resolves to nothing in the schema's own namespace
    is a defect in the schema, and telling the user to load more files would mislead."""
    model = parse_single(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:tns="urn:t" '
        b'targetNamespace="urn:t"><xs:element name="A" type="tns:Missing"/></xs:schema>',
        "a.xsd",
    )

    with pytest.raises(ValidationSetupError) as raised:
        build_xmlschema(model)

    assert str(raised.value).startswith("the schema itself is not valid XSD: ")


# ---------------------------------------------------------------------------
# XSD 1.1 (xmlschema, in a worker process)
# ---------------------------------------------------------------------------

_XS = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
_RANGE_XSD = (
    f"<xs:schema {_XS}>\n"
    '<xs:element name="Range"><xs:complexType><xs:sequence>\n'
    '<xs:element name="Min" type="xs:int"/>\n'
    '<xs:element name="Max" type="xs:int"/>\n'
    '<xs:element name="Ref" type="xs:IDREF" minOccurs="0"/>\n'
    "</xs:sequence>\n"
    '<xs:assert test="Min le Max"/>\n'
    "</xs:complexType></xs:element>\n"
    "</xs:schema>"
).encode()


def test_an_xsd_11_schema_is_validated_assertions_included() -> None:
    model = parse_single(_RANGE_XSD, "range.xsd")
    assert model.xsd_version == "1.1"

    valid = validate_xml(model, b"<Range><Min>1</Min><Max>2</Max></Range>")
    invalid = validate_xml(model, b"<Range><Min>5</Min><Max>2</Max></Range>")

    assert valid.is_valid and valid.validator == "xmlschema"
    assert valid.reformatted_xml is not None and "<Min>1</Min>" in valid.reformatted_xml
    (error,) = invalid.errors
    assert not invalid.is_valid
    # Which assertion failed, and on which line of the reformatted text.
    assert error.message == "assertion test is false: Min le Max"
    assert (error.line, error.path, error.domain) == (2, "/Range", "xmlschema")
    assert error.xsd_ref is not None and error.xsd_ref.id == "element:Range"


def test_xsd_11_errors_point_at_the_offending_child_and_check_idrefs() -> None:
    """libxml2 never checks that an IDREF names an ID; the 1.1 validator does."""
    model = parse_single(_RANGE_XSD, "range.xsd")

    result = validate_xml(model, b"<Range><Min>1</Min><Oops/><Max>2</Max><Ref>nowhere</Ref></Range>")

    by_line = {error.line: error.message for error in result.errors}
    assert "Oops" in by_line[4]  # the unexpected child, not its parent on line 2
    assert any("IDREF 'nowhere' not found" in message for message in by_line.values())


def test_a_document_that_is_not_well_formed_is_reported_as_such_under_xsd_11() -> None:
    model = parse_single(_RANGE_XSD, "range.xsd")

    result = validate_xml(model, b"<Range><Min>1</Range>")

    (error,) = result.errors
    assert error.kind == "not-well-formed" and result.reformatted_xml is None


def test_a_schema_the_version_heuristic_takes_for_1_0_still_reaches_the_1_1_validator() -> None:
    """xs:dateTimeStamp is a 1.1 type and nothing else here is: libxml2 refuses the
    schema, and "the schema itself is not valid XSD" would be wrong."""
    model = parse_single(
        f'<xs:schema {_XS}><xs:element name="At" type="xs:dateTimeStamp"/></xs:schema>'.encode(),
        "at.xsd",
    )
    assert model.xsd_version != "1.1"

    valid = validate_xml(model, b"<At>2024-01-01T00:00:00Z</At>")
    invalid = validate_xml(model, b"<At>2024-01-01T00:00:00</At>")

    assert valid.is_valid and valid.validator == "xmlschema"
    assert not invalid.is_valid and "time zone" in invalid.errors[0].message


def test_a_broken_1_0_schema_keeps_libxml2s_complaint() -> None:
    """The 1.1 validator refuses it as well, and its wording is the less familiar one."""
    model = parse_single(
        f'<xs:schema {_XS} xmlns:tns="urn:t" targetNamespace="urn:t">'
        '<xs:element name="A" type="tns:Missing"/></xs:schema>'.encode(),
        "a.xsd",
    )

    with pytest.raises(ValidationSetupError) as raised:
        validate_xml(model, b'<A xmlns="urn:t"/>')

    assert str(raised.value).startswith("the schema itself is not valid XSD: ")


def test_a_broken_xsd_11_schema_says_where() -> None:
    model = parse_single(
        f"<xs:schema {_XS}>\n"
        '<xs:element name="A"><xs:complexType>\n'
        '<xs:assert test="count(("/>\n'
        "</xs:complexType></xs:element></xs:schema>".encode(),
        "broken.xsd",
    )

    with pytest.raises(ValidationSetupError) as raised:
        validate_xml(model, b"<A/>")

    message = str(raised.value)
    assert message.startswith("the schema itself is not valid XSD 1.1: broken.xsd: ")
    assert "XPST0003" in message  # the XPath syntax error
    assert "/tmp" not in message and "xsdval-" not in message


def test_an_xsd_11_schema_in_several_files_is_read_from_the_loaded_copies() -> None:
    """The worker may read nothing but the materialised files: an include by relative
    path resolves there, and so does an import the loader found under a Windows path."""
    files = {
        "main.xsd": (
            f'<xs:schema {_XS} xmlns:p="urn:p" xmlns:t="urn:t" targetNamespace="urn:t" '
            'elementFormDefault="qualified">'
            '<xs:include schemaLocation="parts/types.xsd"/>'
            '<xs:import namespace="urn:p" schemaLocation="Other\\Part.xsd"/>'
            '<xs:element name="Doc"><xs:complexType><xs:sequence>'
            '<xs:element name="Count" type="t:Positive"/><xs:element ref="p:Part"/>'
            "</xs:sequence></xs:complexType></xs:element></xs:schema>"
        ).encode(),
        "parts/types.xsd": (
            f'<xs:schema {_XS} targetNamespace="urn:t">'
            '<xs:simpleType name="Positive"><xs:restriction base="xs:int">'
            '<xs:assertion test="$value gt 0"/></xs:restriction></xs:simpleType></xs:schema>'
        ).encode(),
        "other/part.xsd": (
            f'<xs:schema {_XS} targetNamespace="urn:p"><xs:element name="Part" type="xs:string"/>'
            "</xs:schema>"
        ).encode(),
    }
    model = parse_files_map(files, "main.xsd")
    assert model.xsd_version == "1.1"
    doc = '<Doc xmlns="urn:t"><Count>{}</Count><Part xmlns="urn:p">x</Part></Doc>'

    assert validate_xml(model, doc.format(3).encode()).is_valid
    (error,) = validate_xml(model, doc.format(0).encode()).errors
    assert "$value gt 0" in error.message


def test_an_assertion_cannot_read_files_or_the_servers_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The test of an xs:assert is the schema author's XPath, run on our server."""
    monkeypatch.setenv("USAGE_DB_PASSWORD", "hunter2")
    model = parse_single(
        f'<xs:schema {_XS}><xs:element name="A"><xs:complexType>'
        "<xs:assert test=\"not(doc-available('file:///etc/hostname'))\"/>"
        "<xs:assert test=\"doc('file:///etc/passwd')\"/>"
        "</xs:complexType></xs:element></xs:schema>".encode(),
        "probe.xsd",
    )

    result = validate_xml(model, b"<A/>")

    (error,) = result.errors  # the first assertion holds: no document is reachable
    assert "FODC0002" in error.message
    assert "hunter2" not in str(result) and "root:" not in str(result)


def test_an_xsd_11_validation_that_runs_too_long_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation.settings, "xsd11_timeout_seconds", 0.01)
    model = parse_single(_RANGE_XSD, "range.xsd")

    with pytest.raises(ValidationSetupError, match="took longer than 0.01 s"):
        validate_xml(model, b"<Range><Min>1</Min><Max>2</Max></Range>")


def test_a_worker_that_runs_out_of_memory_is_a_setup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation.settings, "xsd11_memory_mb", 16)
    model = parse_single(_RANGE_XSD, "range.xsd")

    with pytest.raises(ValidationSetupError, match="time or memory limits"):
        validate_xml(model, b"<Range><Min>1</Min><Max>2</Max></Range>")


def test_without_the_xsd_11_validator_the_old_explanation_stays(monkeypatch: pytest.MonkeyPatch) -> None:
    def _missing(*_args):  # noqa: ANN002, ANN202
        raise validation._Xsd11UnavailableError("No module named 'xmlschema'")

    monkeypatch.setattr(validation, "_run_worker", _missing)
    model = parse_single(_RANGE_XSD, "range.xsd")

    with pytest.raises(ValidationSetupError, match="libxml2, which implements XSD 1.0 only"):
        validate_xml(model, b"<Range><Min>1</Min><Max>2</Max></Range>")
