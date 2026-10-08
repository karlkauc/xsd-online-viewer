"""Samples must validate: one minimal schema per construct the generator used to get wrong.

Every document is checked with libxml2 and, when the dev extra is installed,
with ``xmlschema`` as a second opinion: it knows XSD 1.1 and it checks that
an IDREF points at an ID, which libxml2 does not.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from app.parser.sample import SampleOptions, generate_sample_with_report
from app.parser.xsd_parser import parse_single

try:
    import xmlschema
except ImportError:  # the dev extra is optional
    xmlschema = None

NS = "urn:t"
FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parents[2]


def _schema(body: str, *, attrs: str = 'elementFormDefault="qualified"') -> bytes:
    return (
        '<?xml version="1.0"?>'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'xmlns:t="{NS}" targetNamespace="{NS}" {attrs}>'
        f"{body}</xs:schema>"
    ).encode()


def _generate(xsd: bytes, element: int | str = 0, **options) -> tuple[str, dict[str, int]]:
    model = parse_single(xsd, "t.xsd")
    declaration = (
        model.elements[element]
        if isinstance(element, int)
        else next(e for e in model.elements if e.name == element)
    )
    xml, report = generate_sample_with_report(model, declaration, SampleOptions(**options))
    return xml, report.counts


def _errors(xsd: bytes, xml: str) -> list[str]:
    schema = etree.XMLSchema(etree.fromstring(xsd))
    document = etree.fromstring(xml.encode("utf-8"))
    errors = [] if schema.validate(document) else [e.message for e in schema.error_log]
    if xmlschema is not None:
        errors += [str(e.reason) for e in xmlschema.XMLSchema10(xsd.decode()).iter_errors(xml)]
    return errors


def _valid_sample(body: str, element: int | str = 0, **options) -> tuple[etree._Element, dict[str, int]]:
    """Generate for ``body`` and insist the result validates."""
    xsd = _schema(body)
    xml, counts = _generate(xsd, element, **options)
    assert _errors(xsd, xml) == [], xml
    return etree.fromstring(xml.encode("utf-8")), counts


def _children(root: etree._Element) -> list[etree._Element]:
    """Child elements, without the comments the generator leaves."""
    return [child for child in root if isinstance(child.tag, str)]


def _simple(name: str, base: str, facets: str) -> str:
    return (
        f'<xs:simpleType name="{name}"><xs:restriction base="{base}">'
        f"{facets}</xs:restriction></xs:simpleType>"
    )


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_circular_simple_content_does_not_crash(id_idref_xsd_bytes: bytes) -> None:
    xml, counts = _generate(id_idref_xsd_bytes, "ComplexCycleElement")
    assert counts.get("simple_recursion") == 1
    etree.fromstring(xml.encode("utf-8"))


@pytest.mark.parametrize(
    "types",
    [
        '<xs:simpleType name="A"><xs:union memberTypes="t:B"/></xs:simpleType>'
        '<xs:simpleType name="B"><xs:union memberTypes="t:A"/></xs:simpleType>',
        '<xs:simpleType name="A"><xs:list itemType="t:B"/></xs:simpleType>'
        '<xs:simpleType name="B"><xs:list itemType="t:A"/></xs:simpleType>',
    ],
)
def test_circular_simple_types_do_not_crash(types: str) -> None:
    xml, counts = _generate(_schema('<xs:element name="R" type="t:A"/>' + types))
    assert counts.get("simple_recursion") == 1
    etree.fromstring(xml.encode("utf-8"))


def test_deeply_nested_required_content_does_not_crash() -> None:
    levels = 130
    body = '<xs:element name="R" type="t:T0"/>'
    for level in range(levels):
        body += (
            f'<xs:complexType name="T{level}"><xs:choice><xs:sequence>'
            f'<xs:element name="e{level}" type="t:T{level + 1}"/>'
            "</xs:sequence></xs:choice></xs:complexType>"
        )
    body += f'<xs:complexType name="T{levels}"><xs:sequence/></xs:complexType>'
    xsd = _schema(body)
    xml, counts = _generate(xsd)
    etree.fromstring(xml.encode("utf-8"))
    assert counts.get("depth_limit") == 1
    # With the depth guard out of the way the whole chain comes out, and validates.
    xml, counts = _generate(xsd, max_depth=200)
    assert "depth_limit" not in counts
    assert _errors(xsd, xml) == []


def test_required_repetitions_respect_the_element_budget() -> None:
    xml, counts = _generate(
        _schema(
            '<xs:element name="R"><xs:complexType><xs:sequence>'
            '<xs:element name="row" minOccurs="400" maxOccurs="unbounded"><xs:complexType><xs:sequence>'
            '<xs:element name="cell" type="xs:int" minOccurs="400" maxOccurs="unbounded"/>'
            "</xs:sequence></xs:complexType></xs:element>"
            "</xs:sequence></xs:complexType></xs:element>"
        )
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert sum(1 for _ in root.iter(etree.Element)) < 12_000
    assert counts["required_occurrences_cut"] >= 1
    assert counts["size_limit"] == 1
    assert "sample truncated: size limit" in xml


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_repeat_never_exceeds_max_occurs() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="a" type="xs:int" minOccurs="0" maxOccurs="2"/>'
        '<xs:element name="b" type="xs:int" maxOccurs="unbounded"/>'
        '<xs:element name="c" type="xs:int"/>'
        "</xs:sequence></xs:complexType></xs:element>",
        include_optional=True,
        repeat=3,
    )
    assert [etree.QName(child).localname for child in root] == ["a", "a", "b", "b", "b", "c"]


def test_repeated_choice_shows_its_branches() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:choice maxOccurs="unbounded">'
        '<xs:element name="a" type="xs:int"/>'
        '<xs:element name="b" type="xs:int"/>'
        "</xs:choice></xs:complexType></xs:element>",
        include_optional=True,
        repeat=3,
    )
    assert [etree.QName(child).localname for child in root] == ["a", "b", "a"]


def test_fixed_element_keeps_the_attributes_of_its_type() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R" type="t:T" fixed="EUR"/>'
        '<xs:complexType name="T"><xs:simpleContent><xs:extension base="xs:string">'
        '<xs:attribute name="a" type="xs:int" use="required"/>'
        "</xs:extension></xs:simpleContent></xs:complexType>"
    )
    assert root.text == "EUR"
    assert root.get("a") == "1"


def test_default_applies_to_simple_content() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R" type="t:T" default="X"/>'
        '<xs:complexType name="T"><xs:simpleContent><xs:extension base="xs:string">'
        '<xs:attribute name="a" type="xs:int"/>'
        "</xs:extension></xs:simpleContent></xs:complexType>"
    )
    assert root.text == "X"


def test_empty_fixed_attribute_value_is_kept() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType>'
        '<xs:attribute name="a" type="xs:string" fixed="" use="required"/>'
        "</xs:complexType></xs:element>"
    )
    assert root.get("a") == ""


def test_substitution_member_without_a_type_takes_the_heads_type() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element ref="t:Head"/>'
        "</xs:sequence></xs:complexType></xs:element>"
        '<xs:element name="Head" type="t:T" abstract="true"/>'
        '<xs:element name="Member" substitutionGroup="t:Head"/>'
        '<xs:complexType name="T"><xs:sequence>'
        '<xs:element name="x" type="xs:int"/>'
        "</xs:sequence></xs:complexType>"
    )
    member = root[0]
    assert etree.QName(member).localname == "Member"
    assert len(member) == 1


def test_extending_any_type_is_not_a_missing_base() -> None:
    _, counts = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:complexContent>'
        '<xs:extension base="xs:anyType"><xs:attribute name="a" type="xs:int" use="required"/>'
        "</xs:extension></xs:complexContent></xs:complexType></xs:element>"
    )
    assert counts == {}


def test_optional_element_around_an_unfillable_required_wildcard_is_left_out() -> None:
    root, counts = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="a" type="xs:int"/>'
        '<xs:element name="extension" minOccurs="0"><xs:complexType><xs:sequence>'
        '<xs:any namespace="##other" maxOccurs="unbounded"/>'
        "</xs:sequence></xs:complexType></xs:element>"
        "</xs:sequence></xs:complexType></xs:element>",
        include_optional=True,
    )
    assert [etree.QName(child).localname for child in _children(root)] == ["a"]
    assert counts == {"optional_subtree_dropped": 1}


def test_exact_length_with_an_open_pattern() -> None:
    root, counts = _valid_sample(
        '<xs:element name="R" type="t:T"/>'
        + _simple("T", "xs:string", '<xs:length value="6"/><xs:pattern value="\\d*[1-9]\\d*"/>')
    )
    assert counts == {} and len(root.text) == 6


def test_identical_comments_in_a_row_are_merged() -> None:
    xml, _ = _generate(
        _schema(
            '<xs:element name="R"><xs:complexType><xs:sequence>'
            '<xs:any minOccurs="0" maxOccurs="unbounded" processContents="lax"/>'
            "</xs:sequence></xs:complexType></xs:element>"
        ),
        include_optional=True,
        repeat=3,
    )
    assert xml.count("any element allowed here") == 1


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def _element_of(type_definition: str) -> str:
    return '<xs:element name="R" type="t:T"/>' + type_definition


def test_patterns_of_two_derivation_steps_must_both_match() -> None:
    root, counts = _valid_sample(
        _element_of(
            _simple("Base", "xs:string", '<xs:pattern value="[A-Z0-9]{4}"/>')
            + _simple("T", "t:Base", '<xs:pattern value="[0-9A-F]+"/>')
        )
    )
    assert counts == {}
    assert len(root.text) == 4


def test_patterns_of_one_step_are_alternatives() -> None:
    root, counts = _valid_sample(
        _element_of(
            _simple(
                "T",
                "xs:string",
                '<xs:pattern value="[A-Z]{2}"/><xs:pattern value="[0-9]{5}"/><xs:minLength value="3"/>',
            )
        )
    )
    assert counts == {}
    assert root.text.isdigit()


@pytest.mark.parametrize(
    ("base", "facets"),
    [
        ("xs:string", '<xs:pattern value="A|BBBBB"/><xs:minLength value="3"/>'),
        ("xs:string", '<xs:pattern value="\\p{Lu}{3}\\p{Nd}{2}"/>'),
        ("xs:string", '<xs:pattern value="[\\p{L}\\p{N}]{2,}"/>'),
        ("xs:decimal", '<xs:pattern value="[+-][0-9]+\\.[0-9]{4}"/><xs:minInclusive value="5"/>'),
        ("xs:dateTime", '<xs:pattern value=".*\\.\\d{6}Z"/>'),
        ("xs:decimal", '<xs:minExclusive value="0"/><xs:maxExclusive value="0.05"/>'),
        ("xs:float", '<xs:maxInclusive value="1E-5"/><xs:minExclusive value="0"/>'),
        ("xs:date", '<xs:minExclusive value="2030-01-01"/>'),
        ("xs:date", '<xs:maxExclusive value="2020-01-01"/>'),
        ("xs:dateTime", '<xs:minExclusive value="2030-01-01T00:00:00Z"/>'),
        ("xs:time", '<xs:minExclusive value="12:00:00"/>'),
        ("xs:gYear", '<xs:maxExclusive value="2000"/>'),
        ("xs:duration", '<xs:minExclusive value="P5D"/>'),
        ("xs:NMTOKENS", '<xs:minLength value="3"/>'),
        ("xs:IDREFS", '<xs:length value="2"/>'),
        ("xs:ID", '<xs:pattern value="[A-Z]{3}-\\d+"/>'),
        ("xs:ID", '<xs:maxLength value="2"/>'),
    ],
)
def test_facets_are_satisfied(base: str, facets: str) -> None:
    body = (
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="v" type="t:T"/>'
        '</xs:sequence><xs:attribute name="id" type="xs:ID" use="required"/>'
        "</xs:complexType></xs:element>"
        + _simple("T", base, facets)
    )
    _, counts = _valid_sample(body)
    assert counts == {}


@pytest.mark.parametrize(
    ("item_type", "restriction"),
    [
        ("xs:token", '<xs:enumeration value="a b"/><xs:enumeration value="c d e"/>'),
        ("xs:int", '<xs:pattern value="\\d+ \\d+ \\d+"/>'),
        ("xs:int", '<xs:minLength value="2"/><xs:maxLength value="4"/>'),
    ],
)
def test_restricted_list(item_type: str, restriction: str) -> None:
    _valid_sample(
        _element_of(
            f'<xs:simpleType name="L"><xs:list itemType="{item_type}"/></xs:simpleType>'
            + _simple("T", "t:L", restriction)
        )
    )


def test_restriction_of_an_anonymous_base_type() -> None:
    root, _ = _valid_sample(
        _element_of(
            '<xs:simpleType name="T"><xs:restriction>'
            '<xs:simpleType><xs:list itemType="xs:NCName"/></xs:simpleType>'
            '<xs:minLength value="2"/></xs:restriction></xs:simpleType>'
        )
    )
    assert len(root.text.split()) == 2


def test_simple_content_restricted_through_an_anonymous_type() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R" type="t:T"/>'
        '<xs:complexType name="Base"><xs:simpleContent><xs:extension base="xs:string">'
        '<xs:attribute name="a" type="xs:int"/></xs:extension></xs:simpleContent></xs:complexType>'
        '<xs:complexType name="T"><xs:simpleContent><xs:restriction base="t:Base">'
        '<xs:simpleType><xs:restriction base="xs:string">'
        '<xs:enumeration value="ZZ"/></xs:restriction></xs:simpleType>'
        "</xs:restriction></xs:simpleContent></xs:complexType>"
    )
    assert root.text == "ZZ"


def test_restricted_union_falls_through_to_a_member_that_fits() -> None:
    root, counts = _valid_sample(
        _element_of(
            '<xs:simpleType name="U"><xs:union memberTypes="xs:int xs:string"/></xs:simpleType>'
            + _simple("T", "t:U", '<xs:pattern value="[a-z]{4}"/>')
        )
    )
    assert counts == {}
    assert root.text.isalpha()


def test_enumerated_ids_are_not_handed_out_twice() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="a" type="t:T"/><xs:element name="b" type="t:T"/>'
        "</xs:sequence></xs:complexType></xs:element>"
        + _simple("T", "xs:ID", '<xs:enumeration value="x"/><xs:enumeration value="y"/>')
    )
    assert [child.text for child in root] == ["x", "y"]


# ---------------------------------------------------------------------------
# ID / IDREF
# ---------------------------------------------------------------------------

needs_xmlschema = pytest.mark.skipif(xmlschema is None, reason="xmlschema (dev extra) not installed")


@needs_xmlschema
def test_idref_points_at_an_id_in_the_document() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="ref" type="xs:IDREF"/>'
        '<xs:element name="refs" type="xs:IDREFS"/>'
        '<xs:element name="item" maxOccurs="unbounded"><xs:complexType>'
        '<xs:attribute name="id" type="xs:ID" use="required"/></xs:complexType></xs:element>'
        "</xs:sequence></xs:complexType></xs:element>",
        include_optional=True,
        repeat=2,
    )
    ids = [item.get("id") for item in root.findall(f"{{{NS}}}item")]
    assert root.find(f"{{{NS}}}ref").text in ids


@needs_xmlschema
def test_optional_idref_is_left_out_when_there_is_no_id() -> None:
    root, counts = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="ref" type="xs:IDREF" minOccurs="0"/>'
        "</xs:sequence><xs:attribute name=\"other\" type=\"xs:IDREF\"/></xs:complexType></xs:element>",
        include_optional=True,
    )
    assert _children(root) == [] and "other" not in root.attrib
    assert counts == {"optional_subtree_dropped": 1}


def test_required_idref_without_any_id_is_reported() -> None:
    _, counts = _generate(_schema('<xs:element name="R" type="xs:IDREF"/>'))
    assert counts == {"idref_without_id": 1}


# ---------------------------------------------------------------------------
# Identity constraints
# ---------------------------------------------------------------------------


def _unique_over(item_type: str, types: str = "", occurs: str = 'maxOccurs="unbounded"') -> str:
    return (
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        f'<xs:element name="i" type="{item_type}" minOccurs="1" {occurs}/>'
        "</xs:sequence></xs:complexType>"
        '<xs:unique name="u"><xs:selector xpath="t:i"/><xs:field xpath="."/></xs:unique>'
        "</xs:element>" + types
    )


@pytest.mark.parametrize("item_type", ["xs:boolean", "xs:date", "xs:dateTime", "xs:decimal"])
def test_unique_values_differ_in_the_value_space(item_type: str) -> None:
    root, _ = _valid_sample(_unique_over(item_type), include_optional=True, repeat=3)
    # Three booleans cannot differ; the surplus occurrence goes.
    assert len(_children(root)) == (2 if item_type == "xs:boolean" else 3)


def test_surplus_occurrences_go_when_the_type_runs_out_of_values() -> None:
    root, counts = _valid_sample(
        _unique_over(
            "t:T", _simple("T", "xs:string", '<xs:enumeration value="a"/><xs:enumeration value="b"/>')
        ),
        include_optional=True,
        repeat=3,
    )
    assert [child.text for child in _children(root)] == ["a", "b"]
    assert "identity_value_not_unique" not in counts


def test_key_on_an_optional_attribute_makes_it_appear() -> None:
    root, counts = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="i" maxOccurs="unbounded"><xs:complexType>'
        '<xs:attribute name="k" type="xs:int"/></xs:complexType></xs:element>'
        "</xs:sequence></xs:complexType>"
        '<xs:key name="k"><xs:selector xpath="t:i"/><xs:field xpath="@k"/></xs:key>'
        "</xs:element>"
    )
    assert root[0].get("k") is not None
    assert counts == {}


# ---------------------------------------------------------------------------
# Plausible values
# ---------------------------------------------------------------------------


def test_names_suggest_values_that_still_have_to_fit_the_type() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="Currency" type="xs:string"/>'
        '<xs:element name="SystemCountry" type="t:Two"/>'
        '<xs:element name="Email" type="xs:string"/>'
        '<xs:element name="ISIN" type="t:Isin"/>'
        '<xs:element name="CountryCode" type="t:Digits"/>'
        '<xs:element name="Hotel" type="xs:string"/>'
        "</xs:sequence></xs:complexType></xs:element>"
        + _simple("Two", "xs:string", '<xs:pattern value="[A-Z]{2}"/>')
        + _simple("Isin", "xs:string", '<xs:pattern value="[A-Z]{2}[A-Z0-9]{9}[0-9]"/>')
        + _simple("Digits", "xs:string", '<xs:pattern value="[0-9]{3}"/>')
    )
    values = {etree.QName(child).localname: child.text for child in root}
    assert values == {
        "Currency": "EUR",
        "SystemCountry": "AT",
        "Email": "max.mustermann@example.com",
        "ISIN": "US0378331005",
        "CountryCode": "012",  # no hint fits three digits, so the pattern decides
        "Hotel": "string",  # "tel" inside a word is not a phone number
    }


def test_repeated_values_vary() -> None:
    root, _ = _valid_sample(
        '<xs:element name="R"><xs:complexType><xs:sequence>'
        '<xs:element name="d" type="xs:date" maxOccurs="3"/>'
        '<xs:element name="n" type="xs:decimal" maxOccurs="3"/>'
        '<xs:element name="i" type="xs:int" maxOccurs="3"/>'
        '<xs:element name="Currency" type="xs:string" maxOccurs="3"/>'
        "</xs:sequence></xs:complexType></xs:element>",
        include_optional=True,
        repeat=3,
    )
    assert [child.text for child in root] == [
        "2026-01-01", "2026-01-02", "2026-01-03",
        "0.0", "1.5", "2.75",
        "1", "2", "3",
        "EUR", "USD", "CHF",
    ]  # fmt: skip


def test_pattern_samples_are_not_empty_when_they_need_not_be() -> None:
    root, _ = _valid_sample(_element_of(_simple("T", "xs:string", '<xs:pattern value="[A-Z]*"/>')))
    assert root.text == "A"


def test_default_namespace_is_used_when_the_schema_uses_it() -> None:
    xsd = (
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns="urn:t" '
        b'targetNamespace="urn:t" elementFormDefault="qualified">'
        b'<xs:element name="R"><xs:complexType><xs:sequence>'
        b'<xs:element name="a" type="xs:int"/>'
        b"</xs:sequence></xs:complexType></xs:element></xs:schema>"
    )
    xml, _ = _generate(xsd)
    assert '<R xmlns="urn:t">' in xml and "<a>1</a>" in xml
    assert _errors(xsd, xml) == []
    # An unqualified local element is in no namespace, so the prefix has to stay.
    unqualified = xsd.replace(b' elementFormDefault="qualified"', b"")
    xml, _ = _generate(unqualified)
    assert "<ns1:R" in xml and "<a>1</a>" in xml
    assert _errors(unqualified, xml) == []


@pytest.mark.parametrize(
    ("test", "children"),
    [
        # A general comparison casts the untyped attribute to a number: status="1" selects Ok.
        ("@status &lt; 300", ["id", "data"]),
        # A value comparison with a number is a type error, so the alternative never applies.
        ("@status lt 300", ["id"]),
    ],
)
def test_type_alternative_follows_the_generated_attributes(test: str, children: list[str]) -> None:
    """XSD 1.1: libxml2 cannot compile this, so only the second validator checks it."""
    xsd = _schema(
        '<xs:element name="R">'
        f'<xs:alternative test="{test}" type="t:Ok"/>'
        '<xs:alternative type="t:Base"/>'
        "</xs:element>"
        '<xs:complexType name="Base"><xs:sequence><xs:element name="id" type="xs:int"/></xs:sequence>'
        '<xs:attribute name="status" type="xs:positiveInteger" use="required"/></xs:complexType>'
        '<xs:complexType name="Ok"><xs:complexContent><xs:extension base="t:Base"><xs:sequence>'
        '<xs:element name="data" type="xs:int"/>'
        "</xs:sequence></xs:extension></xs:complexContent></xs:complexType>"
    )
    xml, counts = _generate(xsd)
    root = etree.fromstring(xml.encode("utf-8"))
    assert [etree.QName(child).localname for child in root] == children
    assert counts == {}
    if xmlschema is not None:
        assert [str(e.reason) for e in xmlschema.XMLSchema11(xsd.decode()).iter_errors(xml)] == []


# ---------------------------------------------------------------------------
# Real schemas, second validator
# ---------------------------------------------------------------------------

XSD_11_SCHEMAS = [
    "samples/xsd-1.1/api-envelope.xsd",
    "samples/xsd-1.1/measurement.xsd",
    "samples/xsd-1.1/plugin-config-base.xsd",
    "samples/keys-and-ids/order-registry.xsd",
    "backend/tests/fixtures/alternatives.xsd",
    "backend/tests/fixtures/vc-versioning.xsd",
    "backend/tests/fixtures/idroles-main.xsd",
]


@needs_xmlschema
@pytest.mark.parametrize("path", XSD_11_SCHEMAS)
@pytest.mark.parametrize("include_optional", [False, True])
def test_samples_validate_with_the_xsd_11_validator(path: str, include_optional: bool) -> None:
    from app.parser.xsd_parser import parse_files_map

    source = REPO / path
    files = {p.name: p.read_bytes() for p in source.parent.glob("*.xsd") if p.stat().st_size < 1_000_000}
    files = {n: c for n, c in files.items() if n not in ("billion_laughs.xsd", "xxe_attack.xsd")}
    model = parse_files_map(files, source.name)
    schema = xmlschema.XMLSchema11(str(source), allow="local")
    main = model.files[0].id
    roots = [e for e in model.elements if e.name and e.source_ref and e.source_ref.file_id == main]
    assert roots
    for root in roots:
        xml, report = generate_sample_with_report(
            model, root, SampleOptions(include_optional=include_optional)
        )
        if "idref_without_id" in report.counts:
            continue  # a lone IDREF root can never validate, and the report says so
        assert [str(e.reason) for e in schema.iter_errors(xml)] == [], xml
