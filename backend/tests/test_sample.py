"""Sample XML generation (app/parser/sample.py)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from app.parser.sample import (
    GENERATOR_LIMIT,
    SampleOptions,
    find_element,
    generate_sample,
    generate_sample_with_report,
)
from app.parser.validation import validate_xml
from app.parser.xsd_parser import parse_files_map, parse_single, parse_zip

FIXTURES = Path(__file__).parent / "fixtures"


def _sample(model, element_id: str, **kwargs):
    element = find_element(model, element_id)
    assert element is not None, element_id
    xml = generate_sample(model, element, SampleOptions(**kwargs))
    return xml, etree.fromstring(xml.encode("utf-8"))


def test_required_content_only_validates(simple_xsd_bytes: bytes) -> None:
    model = parse_single(simple_xsd_bytes, "simple.xsd")
    xml, root = _sample(model, "element:{http://example.com/simple}Person")
    ns = "{http://example.com/simple}"
    assert root.tag == f"{ns}Person"
    assert [child.tag for child in root] == [f"{ns}FirstName", f"{ns}LastName"]
    assert root.get("id") == "id1"
    assert root.get("country") == "DE"  # default values are shown
    assert xml.startswith("<?xml version='1.0' encoding='UTF-8'?>")
    result = validate_xml(model, xml.encode("utf-8"))
    assert result.is_valid, [e.message for e in result.errors]


def test_optional_content_included_on_request(simple_xsd_bytes: bytes) -> None:
    model = parse_single(simple_xsd_bytes, "simple.xsd")
    xml, root = _sample(
        model, "element:{http://example.com/simple}Person", include_optional=True, repeat=2
    )
    ns = "{http://example.com/simple}"
    tags = [child.tag for child in root]
    assert tags == [f"{ns}FirstName", f"{ns}LastName", f"{ns}Age", f"{ns}Email", f"{ns}Email"]
    assert root.find(f"{ns}Age").text == "0"  # minInclusive of AgeType
    assert validate_xml(model, xml.encode("utf-8")).is_valid


def test_local_element_can_be_the_root(simple_xsd_bytes: bytes) -> None:
    model = parse_single(simple_xsd_bytes, "simple.xsd")
    _, root = _sample(model, "element:anon-3")
    assert root.tag == "{http://example.com/simple}Age"
    assert root.text == "0"


def test_multi_file_schema_with_pattern_facet() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(FIXTURES / "library.xsd", "library.xsd")
        archive.write(FIXTURES / "types.xsd", "types.xsd")
    model = parse_zip(buffer.getvalue(), "library.xsd")
    xml, root = _sample(model, "element:{http://example.com/library}Library")
    ns = "{http://example.com/library}"
    book = root.find(f"{ns}Book")
    assert book is not None
    assert book.find(f"{ns}ISBN").text == "000-0000000000"
    assert validate_xml(model, xml.encode("utf-8")).is_valid


def test_imported_namespace_uses_its_own_prefix(xmldsig_bytes: bytes) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(FIXTURES / "imports-dsig.xsd", "imports-dsig.xsd")
        archive.writestr("xmldsig-core-schema.xsd", xmldsig_bytes)
    model = parse_zip(buffer.getvalue(), "imports-dsig.xsd")
    xml = generate_sample(model, model.elements[0], SampleOptions(include_optional=True))
    root = etree.fromstring(xml.encode("utf-8"))
    dsig = "http://www.w3.org/2000/09/xmldsig#"
    assert any(el.tag.startswith(f"{{{dsig}}}") for el in root.iter(etree.Element))
    assert dsig in root.nsmap.values()


def test_recursion_is_cut_with_a_comment() -> None:
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Node" type="NodeType"/>
  <xs:complexType name="NodeType">
    <xs:sequence>
      <xs:element name="Child" type="NodeType"/>
      <xs:element name="Kind">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:enumeration value="leaf"/>
            <xs:enumeration value="branch"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>
</xs:schema>"""
    model = parse_single(xsd, "rec.xsd")
    _, root = _sample(model, "element:Node")
    assert root.find("Kind").text == "leaf"
    child = root.find("Child")
    assert child is not None
    assert "recursive" in "".join(c.text or "" for c in child.iter(etree.Comment))


def test_choice_takes_first_element_and_abstract_uses_substitution() -> None:
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Shape" abstract="true"/>
  <xs:element name="Circle" substitutionGroup="Shape" type="xs:string"/>
  <xs:element name="Doc">
    <xs:complexType>
      <xs:sequence>
        <xs:choice>
          <xs:sequence><xs:element name="Nested" type="xs:int"/></xs:sequence>
          <xs:element name="B" type="xs:date"/>
          <xs:element name="C" type="xs:boolean"/>
        </xs:choice>
        <xs:element ref="Shape"/>
        <xs:any processContents="lax" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""
    model = parse_single(xsd, "choice.xsd")
    xml, root = _sample(model, "element:Doc")
    assert [c.tag for c in root] == ["B", "Circle"]
    assert root.find("B").text == "2026-01-01"
    assert validate_xml(model, xml.encode("utf-8")).is_valid


@pytest.mark.parametrize(
    ("type_name", "expected"),
    [
        ("xs:positiveInteger", "1"),
        ("xs:boolean", "true"),
        ("xs:dateTime", "2026-01-01T00:00:00"),
        ("xs:anyURI", "http://example.com/"),
    ],
)
def test_builtin_placeholders(type_name: str, expected: str) -> None:
    xsd = f"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="V" type="{type_name}"/>
</xs:schema>""".encode()
    model = parse_single(xsd, "v.xsd")
    _, root = _sample(model, "element:V")
    assert root.text == expected


def test_unprefixed_builtin_types_from_default_namespace_schema() -> None:
    xsd = b"""<?xml version="1.0"?>
<schema xmlns="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t" targetNamespace="urn:t"
        elementFormDefault="qualified">
  <simpleType name="Crypto"><restriction base="base64Binary"/></simpleType>
  <element name="Sig">
    <complexType>
      <sequence><element name="Digest" type="t:Crypto"/><element name="Len" type="integer"/></sequence>
      <attribute name="Id" type="ID" use="required"/>
    </complexType>
  </element>
</schema>"""
    model = parse_single(xsd, "dsig.xsd")
    xml, root = _sample(model, "element:{urn:t}Sig")
    ns = "{urn:t}"
    assert root.get("Id") == "id1"
    assert root.find(f"{ns}Digest").text == "AA=="
    assert root.find(f"{ns}Len").text == "1"
    assert validate_xml(model, xml.encode("utf-8")).is_valid


def test_enumeration_respects_range_facets() -> None:
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="PIK">
    <xs:simpleType>
      <xs:restriction base="xs:int">
        <xs:minInclusive value="1"/><xs:maxInclusive value="2"/>
        <xs:enumeration value="0"/><xs:enumeration value="1"/><xs:enumeration value="2"/>
      </xs:restriction>
    </xs:simpleType>
  </xs:element>
</xs:schema>"""
    model = parse_single(xsd, "pik.xsd")
    xml, root = _sample(model, "element:PIK")
    assert root.text == "1"
    assert validate_xml(model, xml.encode("utf-8")).is_valid


def test_optional_recursive_elements_are_left_out() -> None:
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Company" type="CompanyType"/>
  <xs:complexType name="CompanyType">
    <xs:sequence>
      <xs:element name="Name" type="xs:string"/>
      <xs:element name="Parent" type="CompanyType" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>
</xs:schema>"""
    model = parse_single(xsd, "company.xsd")
    xml, root = _sample(model, "element:Company", include_optional=True)
    assert root.find("Name") is not None
    assert root.find("Parent") is None  # would have been empty, hence invalid
    assert validate_xml(model, xml.encode("utf-8")).is_valid


# A type name that exists as a complexType in the referenced namespace and as a
# simpleType in another one — the shape that made the generator write text into
# an element-only element (seen in the wild on a 10-file customs schema).
_AMBIGUOUS_FILES = {
    "main.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:cat="urn:c:agg:5.24.0"
           xmlns="urn:c:doc" targetNamespace="urn:c:doc" elementFormDefault="qualified">
  <xs:import namespace="urn:c:agg:5.24.0" schemaLocation="new.xsd"/>
  <xs:import namespace="urn:c:agg:5.23.0" schemaLocation="old.xsd"/>
  <xs:element name="Doc"><xs:complexType><xs:sequence>
    <xs:element name="GTDNumber" type="cat:GTDIDType"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>""",
    "new.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns="urn:c:agg:5.24.0"
           targetNamespace="urn:c:agg:5.24.0" elementFormDefault="qualified">
  <xs:complexType name="GTDIDType"><xs:sequence>
    <xs:element name="CustomsCode" type="xs:string"/></xs:sequence></xs:complexType>
</xs:schema>""",
    "old.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns="urn:c:agg:5.23.0"
           targetNamespace="urn:c:agg:5.23.0" elementFormDefault="qualified">
  <xs:simpleType name="GTDIDType"><xs:restriction base="xs:string"/></xs:simpleType>
</xs:schema>""",
}


def test_exact_namespace_beats_a_same_named_type_elsewhere() -> None:
    """An exact ``(namespace, name)`` hit must win over the local-name fallback.

    The fallback exists for undeclared prefixes and chameleon includes, but it
    used to run inside the simpleType lookup *before* the complexType table was
    tried at all. A same-named simpleType in any other namespace then beat the
    correctly referenced complexType, and the generator wrote a text placeholder
    into an element-only element — invalid, and silently so.
    """
    model = parse_files_map(_AMBIGUOUS_FILES, "main.xsd")
    xml, root = _sample(model, "element:{urn:c:doc}Doc")
    number = root.find("{urn:c:doc}GTDNumber")
    assert number is not None
    assert (number.text or "").strip() == ""
    assert [c.tag for c in number] == ["{urn:c:agg:5.24.0}CustomsCode"]
    assert validate_xml(model, xml.encode("utf-8")).is_valid


def test_a_type_found_only_by_local_name_is_reported() -> None:
    """Resolving through the fallback is a guess, so it must not stay silent.

    The prefix is undeclared here, so only the local name can match. The output
    is still the best guess, but the report has to say so — otherwise a wrong
    guess looks like a clean run and never reaches the triage list.
    """
    files = dict(_AMBIGUOUS_FILES)
    files["main.xsd"] = files["main.xsd"].replace(
        b'type="cat:GTDIDType"', b'type="undeclared:GTDIDType"'
    )
    model = parse_files_map(files, "main.xsd")
    element = find_element(model, "element:{urn:c:doc}Doc")
    _, report = generate_sample_with_report(model, element, SampleOptions())
    assert report.counts.get("type_resolved_by_local_name") == 1
    assert [e.category for e in report.entries] == [GENERATOR_LIMIT]
    assert report.entries[0].where == "undeclared:GTDIDType"


# ---------------------------------------------------------------------------
# Found by tools/sample_audit.py over schemas users loaded by URL (2026-09-10)
# ---------------------------------------------------------------------------


def _simple_schema(restriction: str, base: str = "xs:string") -> bytes:
    return f"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="V"><xs:simpleType><xs:restriction base="{base}">
    {restriction}
  </xs:restriction></xs:simpleType></xs:element>
</xs:schema>""".encode()


def test_prohibited_particle_is_never_emitted() -> None:
    """maxOccurs="0" removes a particle; optional mode used to emit it once (goAML)."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Address"><xs:complexType><xs:sequence>
    <xs:element name="City" type="xs:string"/>
    <xs:element name="Geo" type="xs:string" minOccurs="0" maxOccurs="0"/>
    <xs:element name="Comments" type="xs:string" minOccurs="0"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "address.xsd")
    xml, root = _sample(model, "element:Address", include_optional=True)
    assert [child.tag for child in root] == ["City", "Comments"]
    assert validate_xml(model, xml.encode("utf-8")).is_valid


@pytest.mark.parametrize("pattern", ["[a-zA-Z0-9-]*", "\\d{0,5}"])
def test_pattern_sample_meets_min_length(pattern: str) -> None:
    """The shortest match of ``x*`` is empty, which minLength rejects (AEAT modelo 170)."""
    model = parse_single(
        _simple_schema(
            f'<xs:minLength value="3"/><xs:maxLength value="50"/><xs:pattern value="{pattern}"/>'
        ),
        "v.xsd",
    )
    xml, root = _sample(model, "element:V")
    assert len(root.text or "") >= 3
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


@pytest.mark.parametrize(
    "facets",
    [
        '<xs:minInclusive value="-99999999999999999999.99"/>'
        '<xs:maxInclusive value="99999999999999999999.99"/>'
        '<xs:fractionDigits value="2"/><xs:totalDigits value="22"/>',
        '<xs:minExclusive value="1000"/><xs:maxExclusive value="1001"/>'
        '<xs:fractionDigits value="1"/>',
    ],
)
def test_decimal_value_lies_inside_its_facets(facets: str) -> None:
    """Float arithmetic turned -99999999999999999999.99 into -1E20 (AEAT modelo 170)."""
    model = parse_single(_simple_schema(facets, base="xs:decimal"), "v.xsd")
    xml, _ = _sample(model, "element:V")
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


@pytest.mark.parametrize(
    ("base", "pattern"),
    [
        ("xs:dateTime", ".+Z"),
        ("xs:date", "\\d{4}-\\d{2}-\\d{2}Z"),
        ("xs:decimal", "\\d+\\.\\d{2}"),
    ],
)
def test_pattern_on_a_non_string_builtin_is_honoured(base: str, pattern: str) -> None:
    """Patterns were only read for string types; UCI demands a trailing Z on dateTimes."""
    model = parse_single(_simple_schema(f'<xs:pattern value="{pattern}"/>', base=base), "v.xsd")
    xml, _ = _sample(model, "element:V")
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


_ABSTRACT_TYPE = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t"
           targetNamespace="urn:t" elementFormDefault="qualified">
  <xs:element name="Activity"><xs:complexType><xs:sequence>
    <xs:element name="Creator" type="t:AbstractSource_t"/>
  </xs:sequence></xs:complexType></xs:element>
  <xs:complexType name="AbstractSource_t" abstract="true"><xs:sequence>
    <xs:element name="Name" type="xs:string"/>
  </xs:sequence></xs:complexType>
  <xs:complexType name="Device_t"><xs:complexContent>
    <xs:extension base="t:AbstractSource_t"><xs:sequence>
      <xs:element name="UnitId" type="xs:unsignedInt"/>
    </xs:sequence></xs:extension>
  </xs:complexContent></xs:complexType>
</xs:schema>"""


def test_abstract_type_is_replaced_by_a_derived_type_via_xsi_type() -> None:
    """An element of an abstract type needs xsi:type (Garmin TrainingCenterDatabase)."""
    model = parse_single(_ABSTRACT_TYPE.encode(), "tcx.xsd")
    xml, root = _sample(model, "element:{urn:t}Activity")
    creator = root.find("{urn:t}Creator")
    prefix, _, local = creator.get("{http://www.w3.org/2001/XMLSchema-instance}type").rpartition(":")
    assert local == "Device_t"
    assert creator.nsmap.get(prefix or None) == "urn:t"
    assert [child.tag for child in creator] == ["{urn:t}Name", "{urn:t}UnitId"]
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_abstract_type_without_a_derived_type_is_reported() -> None:
    xsd = _ABSTRACT_TYPE.split("  <xs:complexType name=\"Device_t\">")[0] + "</xs:schema>"
    model = parse_single(xsd.encode(), "tcx.xsd")
    element = find_element(model, "element:{urn:t}Activity")
    _, report = generate_sample_with_report(model, element, SampleOptions())
    assert report.counts == {"abstract_type_without_derivation": 1}


@pytest.mark.parametrize(
    "wildcard",
    [
        'namespace="##other" processContents="lax"',
        'namespace="##any" processContents="skip"',
        'namespace="##local" processContents="lax"',
        'namespace="##targetNamespace" processContents="strict"',
    ],
)
def test_required_wildcard_is_filled(wildcard: str) -> None:
    """A mandatory xs:any used to stay empty, so the parent was incomplete (XBRL segment)."""
    xsd = f"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t"
           targetNamespace="urn:t" elementFormDefault="qualified">
  <xs:element name="Segment"><xs:complexType><xs:sequence>
    <xs:any {wildcard}/>
  </xs:sequence></xs:complexType></xs:element>
  <xs:element name="Member" type="xs:string"/>
</xs:schema>""".encode()
    model = parse_single(xsd, "segment.xsd")
    xml, root = _sample(model, "element:{urn:t}Segment")
    assert len(root) == 1
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def _fan_out_schema(levels: int, width: int) -> bytes:
    parts = [
        '<?xml version="1.0"?><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">',
        '<xs:element name="Root" type="L0"/>',
    ]
    for level in range(levels):
        children = "".join(
            f'<xs:element name="E{level}_{i}" type="L{level + 1}" minOccurs="0"/>' for i in range(width)
        )
        parts.append(
            f'<xs:complexType name="L{level}"><xs:sequence>{children}</xs:sequence></xs:complexType>'
        )
    parts.append(f'<xs:simpleType name="L{levels}"><xs:restriction base="xs:string"/></xs:simpleType>')
    parts.append("</xs:schema>")
    return "".join(parts).encode()


def test_optional_content_stops_at_the_element_budget() -> None:
    """Without a budget, optional fan-out ran for minutes (JATS: 260k elements in 20 s)."""
    model = parse_single(_fan_out_schema(levels=6, width=6), "fan.xsd")
    element = find_element(model, "element:Root")
    xml, report = generate_sample_with_report(
        model, element, SampleOptions(include_optional=True, max_elements=300)
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert sum(1 for _ in root.iter(etree.Element)) <= 300
    assert report.counts == {"size_limit": 1}
    assert validate_xml(model, xml.encode("utf-8")).is_valid


# A main file without elementFormDefault importing a qualified file that uses
# its own default namespace -- the SIRI layout.
_FORM_FILES = {
    "main.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:c="urn:c" targetNamespace="urn:m">
  <xs:import namespace="urn:c" schemaLocation="common.xsd"/>
  <xs:element name="Request" type="c:RequestType"/>
</xs:schema>""",
    "common.xsd": b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns="urn:c"
           targetNamespace="urn:c" elementFormDefault="qualified">
  <xs:complexType name="RequestType"><xs:sequence>
    <xs:element name="Context" type="ContextType"/>
  </xs:sequence></xs:complexType>
  <xs:complexType name="ContextType"><xs:sequence>
    <xs:element name="Address" type="xs:string"/>
  </xs:sequence></xs:complexType>
</xs:schema>""",
}


def test_element_form_and_default_namespace_come_from_the_declaring_file() -> None:
    """SIRI: local elements of the qualified import came out unqualified, and its
    unprefixed type names were only found by guessing."""
    model = parse_files_map(_FORM_FILES, "main.xsd")
    element = find_element(model, "element:{urn:m}Request")
    xml, report = generate_sample_with_report(model, element, SampleOptions())
    root = etree.fromstring(xml.encode("utf-8"))
    assert [child.tag for child in root] == ["{urn:c}Context"]
    assert root[0][0].tag == "{urn:c}Address"
    assert report.counts == {}
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_choice_prefers_a_branch_that_terminates() -> None:
    """JATS alternatives: the first branch nests back into the element and never ends."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:group name="alternatives-model"><xs:choice>
    <xs:element ref="array"/>
    <xs:element ref="code"/>
  </xs:choice></xs:group>
  <xs:element name="alternatives"><xs:complexType>
    <xs:group ref="alternatives-model" maxOccurs="unbounded"/>
  </xs:complexType></xs:element>
  <xs:element name="array"><xs:complexType><xs:sequence>
    <xs:element ref="alternatives"/>
  </xs:sequence></xs:complexType></xs:element>
  <xs:element name="code" type="xs:string"/>
</xs:schema>"""
    model = parse_single(xsd, "jats.xsd")
    element = find_element(model, "element:alternatives")
    xml, report = generate_sample_with_report(model, element, SampleOptions())
    assert report.counts == {}
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_complex_restriction_keeps_the_base_attributes() -> None:
    """XBRL linkbase: a restriction inherits every attribute use it does not prohibit."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="ExtendedType">
    <xs:sequence>
      <xs:element name="Loc" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="type" type="xs:string" use="required" fixed="extended"/>
    <xs:attribute name="role" type="xs:anyURI" use="required"/>
    <xs:attribute name="title" type="xs:string"/>
  </xs:complexType>
  <xs:element name="Link"><xs:complexType><xs:complexContent>
    <xs:restriction base="ExtendedType">
      <xs:sequence>
        <xs:element name="Loc" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
      </xs:sequence>
      <xs:attribute name="title" use="prohibited"/>
    </xs:restriction>
  </xs:complexContent></xs:complexType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "link.xsd")
    xml, root = _sample(model, "element:Link", include_optional=True)
    assert root.get("type") == "extended"
    assert root.get("role") is not None
    assert root.get("title") is None
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_abstract_head_is_substituted_through_an_abstract_member() -> None:
    """SIRI: AbstractServiceRequest > AbstractFunctionalServiceRequest (abstract) > StopMonitoringRequest.

    Only direct, concrete members were looked at, so the chain looked empty and
    the sample kept the abstract element -- blamed on the schema.
    """
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="AbstractRequest" abstract="true" type="xs:string"/>
  <xs:element name="AbstractFunctionalRequest" abstract="true" type="xs:string"
              substitutionGroup="AbstractRequest"/>
  <xs:element name="StopRequest" type="xs:string" substitutionGroup="AbstractFunctionalRequest"/>
  <xs:element name="Service"><xs:complexType><xs:sequence>
    <xs:element ref="AbstractRequest"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "siri.xsd")
    for element_id in ("element:Service", "element:AbstractRequest"):
        element = find_element(model, element_id)
        xml, report = generate_sample_with_report(model, element, SampleOptions())
        root = etree.fromstring(xml.encode("utf-8"))
        assert "StopRequest" in {el.tag for el in root.iter(etree.Element)}, xml
        assert report.counts == {}
        assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_enumeration_on_a_restricted_union_wins() -> None:
    """SIRI DayType: the enumeration restricting a union was dropped for inline members."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="AnyDay"><xs:union>
    <xs:simpleType><xs:restriction base="xs:string">
      <xs:pattern value="pti[0-9]+_[0-9]+"/>
    </xs:restriction></xs:simpleType>
    <xs:simpleType><xs:restriction base="xs:string">
      <xs:enumeration value="monday"/>
    </xs:restriction></xs:simpleType>
  </xs:union></xs:simpleType>
  <xs:element name="DayType"><xs:simpleType>
    <xs:restriction base="AnyDay">
      <xs:enumeration value="monday"/><xs:enumeration value="pti34_0"/>
    </xs:restriction>
  </xs:simpleType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "day.xsd")
    xml, root = _sample(model, "element:DayType")
    assert root.text in {"monday", "pti34_0"}
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_optional_element_of_an_underivable_abstract_type_is_left_out() -> None:
    """UCI ExtensionData: nothing derives from the abstract type, so it cannot be filled.

    The element is optional, so it is left out.
    """
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="ExtensionType" abstract="true"><xs:sequence>
    <xs:element name="Key" type="xs:string"/>
  </xs:sequence></xs:complexType>
  <xs:element name="Policy"><xs:complexType><xs:sequence>
    <xs:element name="Name" type="xs:string"/>
    <xs:element name="ExtensionData" type="ExtensionType" minOccurs="0"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "uci.xsd")
    xml, root = _sample(model, "element:Policy", include_optional=True)
    assert root.find("ExtensionData") is None
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


@pytest.mark.parametrize(
    ("base", "facet"),
    [
        ("xs:hexBinary", '<xs:length value="32"/>'),
        ("xs:base64Binary", '<xs:length value="4"/>'),
        ("xs:hexBinary", '<xs:minLength value="3"/>'),
    ],
)
def test_binary_value_meets_its_length_in_octets(base: str, facet: str) -> None:
    """UCI SHA_2_Hash: the length of hexBinary and base64Binary counts octets."""
    model = parse_single(_simple_schema(facet, base=base), "v.xsd")
    xml, _ = _sample(model, "element:V")
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_most_derived_enumeration_wins() -> None:
    """SIRI DaysOfWeekEnumerationx narrows DayTypeEnumeration; the base's first value is not allowed."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="DayTypeEnumeration"><xs:restriction base="xs:NMTOKEN">
    <xs:enumeration value="pti34_0"/><xs:enumeration value="unknown"/><xs:enumeration value="monday"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="DaysOfWeek"><xs:restriction base="DayTypeEnumeration">
    <xs:enumeration value="unknown"/><xs:enumeration value="monday"/>
  </xs:restriction></xs:simpleType>
  <xs:element name="DayType" type="DaysOfWeek"/>
</xs:schema>"""
    model = parse_single(xsd, "days.xsd")
    xml, root = _sample(model, "element:DayType")
    assert root.text in {"unknown", "monday"}
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


# ---------------------------------------------------------------------------
# Identity constraints (xs:key, xs:keyref, xs:unique)
# ---------------------------------------------------------------------------


def test_unique_values_are_made_distinct() -> None:
    """Every occurrence got the same placeholder, so any unique field collided."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Catalog">
    <xs:complexType><xs:sequence>
      <xs:element name="Item" minOccurs="3" maxOccurs="unbounded"><xs:complexType>
        <xs:attribute name="sku" type="xs:string" use="required"/>
      </xs:complexType></xs:element>
    </xs:sequence></xs:complexType>
    <xs:unique name="uniqueSku"><xs:selector xpath="Item"/><xs:field xpath="@sku"/></xs:unique>
  </xs:element>
</xs:schema>"""
    model = parse_single(xsd, "catalog.xsd")
    element = find_element(model, "element:Catalog")
    xml, report = generate_sample_with_report(model, element, SampleOptions())
    root = etree.fromstring(xml.encode("utf-8"))
    skus = [item.get("sku") for item in root]
    assert len(skus) == 3 and len(set(skus)) == 3, skus
    assert report.counts == {}
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_key_values_stay_inside_their_pattern_when_made_distinct() -> None:
    """XTCE-style: prefixed selector and field, a pattern the new values must still match."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t"
           targetNamespace="urn:t" elementFormDefault="qualified">
  <xs:element name="Workouts">
    <xs:complexType><xs:sequence>
      <xs:element name="Workout" minOccurs="3" maxOccurs="unbounded"><xs:complexType><xs:sequence>
        <xs:element name="Name"><xs:simpleType><xs:restriction base="xs:token">
          <xs:pattern value="[A-Z][0-9]{2}"/>
        </xs:restriction></xs:simpleType></xs:element>
      </xs:sequence></xs:complexType></xs:element>
    </xs:sequence></xs:complexType>
    <xs:key name="workoutKey"><xs:selector xpath="t:Workout"/><xs:field xpath="t:Name"/></xs:key>
  </xs:element>
</xs:schema>"""
    model = parse_single(xsd, "workouts.xsd")
    xml, root = _sample(model, "element:{urn:t}Workouts")
    names = [w.findtext("{urn:t}Name") for w in root]
    assert len(set(names)) == 3, names
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


_KEYREF = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Db">
    <xs:complexType><xs:sequence>
      <xs:element name="Workout" minOccurs="{workouts}" maxOccurs="unbounded"><xs:complexType>
        <xs:attribute name="Name" use="required"><xs:simpleType>
          <xs:restriction base="xs:token"><xs:pattern value="W[0-9]"/></xs:restriction>
        </xs:simpleType></xs:attribute>
      </xs:complexType></xs:element>
      <xs:element name="Ref" minOccurs="{refs}"><xs:complexType><xs:sequence>
        <xs:element name="Id" type="xs:token"/>
      </xs:sequence></xs:complexType></xs:element>
    </xs:sequence></xs:complexType>
    <xs:key name="nameKey"><xs:selector xpath="Workout"/><xs:field xpath="@Name"/></xs:key>
    <xs:keyref name="nameRef" refer="nameKey"><xs:selector xpath="Ref"/><xs:field xpath="Id"/></xs:keyref>
  </xs:element>
</xs:schema>"""


def test_keyref_points_at_an_existing_key() -> None:
    """Garmin TCX: WorkoutNameRef/Id held a placeholder no Workout had as its Name."""
    model = parse_single(_KEYREF.format(workouts=1, refs=1).encode(), "db.xsd")
    element = find_element(model, "element:Db")
    xml, report = generate_sample_with_report(model, element, SampleOptions())
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext("Ref/Id") == root.find("Workout").get("Name")
    assert report.counts == {}
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_optional_keyref_without_any_key_is_left_out() -> None:
    """The key selects nothing that exists, so no value can satisfy an optional keyref."""
    xsd = _KEYREF.format(workouts=1, refs=0).replace(
        '<xs:selector xpath="Workout"/>', '<xs:selector xpath="Retired"/>'
    )
    model = parse_single(xsd.encode(), "db.xsd")
    xml, root = _sample(model, "element:Db", include_optional=True)
    assert root.find("Ref") is None
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_required_keyref_without_any_key_is_reported() -> None:
    model = parse_single(_KEYREF.format(workouts=0, refs=1).encode(), "db.xsd")
    element = find_element(model, "element:Db")
    _, report = generate_sample_with_report(model, element, SampleOptions())
    assert report.counts == {"keyref_without_key": 1}


def test_key_target_without_its_field_is_left_out_when_optional() -> None:
    """XTCE messageNameKey selects MessageSet/*, which also reaches LongDescription."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="MessageSet">
    <xs:complexType><xs:sequence>
      <xs:element name="LongDescription" type="xs:string" minOccurs="0"/>
      <xs:element name="Message" maxOccurs="unbounded"><xs:complexType>
        <xs:attribute name="name" type="xs:string" use="required"/>
      </xs:complexType></xs:element>
    </xs:sequence></xs:complexType>
    <xs:key name="messageNameKey"><xs:selector xpath="*"/><xs:field xpath="@name"/></xs:key>
  </xs:element>
</xs:schema>"""
    model = parse_single(xsd, "xtce.xsd")
    xml, root = _sample(model, "element:MessageSet", include_optional=True)
    assert root.find("LongDescription") is None
    assert root.find("Message") is not None
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


# ---------------------------------------------------------------------------
# Found by the audit and in sample_issue rows (2026-09-11)
# ---------------------------------------------------------------------------

_LIST_XSD = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:l" xmlns="urn:l">
  <xs:simpleType name="NameList"><xs:list itemType="xs:NCName"/></xs:simpleType>
  <xs:simpleType name="Pair">
    <xs:restriction base="NameList"><xs:length value="2"/></xs:restriction>
  </xs:simpleType>
  <xs:simpleType name="AtLeastThree">
    <xs:restriction base="NameList"><xs:minLength value="3"/></xs:restriction>
  </xs:simpleType>
  <xs:complexType name="CodeList"><xs:simpleContent><xs:extension base="NameList">
    <xs:attribute name="codeSpace" type="xs:anyURI"/>
  </xs:extension></xs:simpleContent></xs:complexType>
  <xs:complexType name="CategoryExtent"><xs:simpleContent><xs:restriction base="CodeList">
    <xs:length value="2"/>
  </xs:restriction></xs:simpleContent></xs:complexType>
  <xs:element name="Pair" type="Pair"/>
  <xs:element name="AtLeastThree" type="AtLeastThree"/>
  <xs:element name="CategoryExtent" type="CategoryExtent"/>
</xs:schema>"""


@pytest.mark.parametrize(("name", "items"), [("Pair", 2), ("AtLeastThree", 3), ("CategoryExtent", 2)])
def test_length_facets_on_a_list_count_items(name: str, items: int) -> None:
    """On a list type the length facets count items, not characters (GML CategoryExtent)."""
    model = parse_single(_LIST_XSD, "list.xsd")
    xml, root = _sample(model, f"element:{{urn:l}}{name}")
    assert len((root.text or "").split()) == items, xml
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_unresolved_element_ref_as_root_keeps_its_name() -> None:
    """A sample for a ref whose import is missing came out as <ns1:element/> (UBL cac:*)."""
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:doc" xmlns:cac="urn:cac">
  <xs:import namespace="urn:cac" schemaLocation="missing.xsd"/>
  <xs:element name="Invoice"><xs:complexType><xs:sequence>
    <xs:element ref="cac:Party"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "invoice.xsd")
    element = find_element(model, "element:cac:Party")
    assert element is not None
    xml, report = generate_sample_with_report(model, element, SampleOptions())
    assert etree.fromstring(xml.encode("utf-8")).tag == "{urn:cac}Party", xml
    assert report.counts == {"element_ref_not_found": 1}


def test_complex_content_extension_of_simple_content_keeps_the_text() -> None:
    """GLEIF OtherEntityNameType adds an attribute to NameType through complexContent.

    The content stays NameType's simple content (minLength 1), but the derived
    type itself carries neither a particle nor a simple base, so the element
    came out empty -- invalid, and with nothing in the report.
    """
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:g" xmlns:g="urn:g">
  <xs:simpleType name="Tokenized500">
    <xs:restriction base="xs:token"><xs:minLength value="1"/><xs:maxLength value="500"/></xs:restriction>
  </xs:simpleType>
  <xs:complexType name="NameType"><xs:simpleContent><xs:extension base="g:Tokenized500">
    <xs:attribute name="lang" type="xs:language"/>
  </xs:extension></xs:simpleContent></xs:complexType>
  <xs:complexType name="OtherNameType"><xs:complexContent><xs:extension base="g:NameType">
    <xs:attribute name="type" type="xs:string" use="required"/>
  </xs:extension></xs:complexContent></xs:complexType>
  <xs:element name="OtherName" type="g:OtherNameType"/>
</xs:schema>"""
    model = parse_single(xsd, "lei.xsd")
    xml, root = _sample(model, "element:{urn:g}OtherName")
    assert (root.text or "").strip(), xml
    assert root.get("type") is not None
    assert validate_xml(model, xml.encode("utf-8")).is_valid, xml


def test_report_lists_references_the_loaded_files_do_not_define() -> None:
    """A schema that references what it never loaded cannot compile (UBL without its imports).

    The dialog skips its check for such a sample and names what is missing.
    """
    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:doc" xmlns:cac="urn:cac">
  <xs:import namespace="urn:cac" schemaLocation="missing.xsd"/>
  <xs:element name="Invoice"><xs:complexType><xs:sequence>
    <xs:element ref="cac:Party"/>
    <xs:element name="Total" type="cac:AmountType"/>
    <xs:element ref="cac:Party"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>"""
    model = parse_single(xsd, "invoice.xsd")
    element = find_element(model, "element:{urn:doc}Invoice")
    _, report = generate_sample_with_report(model, element, SampleOptions())
    assert report.missing_references == ["cac:Party", "cac:AmountType"]


def test_a_complete_schema_misses_no_references(simple_xsd_bytes: bytes) -> None:
    model = parse_single(simple_xsd_bytes, "simple.xsd")
    element = find_element(model, "element:{http://example.com/simple}Person")
    _, report = generate_sample_with_report(model, element, SampleOptions(include_optional=True))
    assert report.missing_references == []
