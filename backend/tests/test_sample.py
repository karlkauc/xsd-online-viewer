"""Sample XML generation (app/parser/sample.py)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from app.parser.sample import SampleOptions, find_element, generate_sample
from app.parser.validation import validate_xml
from app.parser.xsd_parser import parse_single, parse_zip

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
