"""schema_diff: what changed between two releases of a schema."""

from __future__ import annotations

from app.parser.schema_diff import diff
from app.parser.xsd_parser import parse_single

OLD = b"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="RootType"/>
  <xs:complexType name="RootType"><xs:sequence>
    <xs:element name="A" type="xs:string"/>
    <xs:element name="B" type="xs:date" minOccurs="0"/>
    <xs:element name="Gone" type="xs:int"/>
    <xs:element name="Nested"><xs:complexType><xs:sequence>
      <xs:element name="X" type="xs:string"/>
    </xs:sequence></xs:complexType></xs:element>
  </xs:sequence></xs:complexType>
  <xs:simpleType name="Code"><xs:restriction base="xs:string">
    <xs:enumeration value="A"/><xs:enumeration value="B"/>
  </xs:restriction></xs:simpleType>
  <xs:complexType name="Old"/>
</xs:schema>"""

NEW = b"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root" type="RootType"/>
  <xs:complexType name="RootType"><xs:sequence>
    <xs:element name="A" type="xs:string"/>
    <xs:element name="B" type="xs:gYear" minOccurs="0" maxOccurs="unbounded"/>
    <xs:element name="New" type="Code" minOccurs="0"/>
    <xs:element name="Nested"><xs:complexType><xs:sequence>
      <xs:element name="X" type="xs:string"/><xs:element name="Y" type="xs:string"/>
    </xs:sequence></xs:complexType></xs:element>
  </xs:sequence></xs:complexType>
  <xs:simpleType name="Code"><xs:restriction base="xs:string">
    <xs:enumeration value="A"/><xs:enumeration value="C"/>
  </xs:restriction></xs:simpleType>
  <xs:complexType name="Fresh"/>
</xs:schema>"""


def test_diff_reports_types_children_and_enumerations() -> None:
    d = diff(parse_single(OLD), parse_single(NEW))
    assert d.added_types == ["Fresh"] and d.removed_types == ["Old"]
    by = {c.container: c for c in d.containers}
    root = by["RootType"]
    assert root.added == ["New (Code, 0..1)"]
    assert root.removed == ["Gone (int, 1..1)"]
    assert root.changed == ["B: date, 0..1 → gYear, 0..*"]
    assert by["RootType/Nested"].added == ["Y (string, 1..1)"]
    assert [(e.type_name, e.added, e.removed) for e in d.enums] == [("Code", ["C"], ["B"])]


def test_identical_schemas_have_no_diff() -> None:
    assert diff(parse_single(OLD), parse_single(OLD)).empty
