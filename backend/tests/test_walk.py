"""Tests for the shared model walker (backend/app/parser/walk.py)."""

from __future__ import annotations

from app.parser.model import AttributeDecl, ElementDecl
from app.parser.walk import iter_attributes, iter_elements
from app.parser.xsd_parser import parse_single


class TestIterElements:
    def test_yields_only_element_decl_instances(self, library_xsd_bytes: bytes) -> None:
        model = parse_single(library_xsd_bytes, "library.xsd")
        assert all(isinstance(e, ElementDecl) for e in iter_elements(model))

    def test_descends_into_nested_content_model(self, library_xsd_bytes: bytes) -> None:
        model = parse_single(library_xsd_bytes, "library.xsd")
        names = {e.name for e in iter_elements(model)}
        # "Book" is a top-level element's particle child; "Title"/"Author" are
        # nested one level deeper inside BookType's own particle.
        assert {"Library", "Book", "Title", "Author", "ISBN"} <= names

    def test_descends_into_alternative_inline_types(
        self, alternatives_xsd_bytes: bytes
    ) -> None:
        model = parse_single(alternatives_xsd_bytes, "alternatives.xsd")
        names = {e.name for e in iter_elements(model)}
        # "Indoor" only exists inside the "cat" xs:alternative's inline
        # complexType — reachable only if iter_elements descends alternatives.
        assert "Indoor" in names


class TestIterAttributes:
    def test_yields_only_attribute_decl_instances(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        assert all(isinstance(a, AttributeDecl) for a in iter_attributes(model))

    def test_yields_attributes_declared_on_complex_types(
        self, simple_xsd_bytes: bytes
    ) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        names = {a.name for a in iter_attributes(model)}
        assert {"id", "country"} <= names

    def test_reaches_attributes_on_inline_complex_types_of_nested_elements(
        self,
    ) -> None:
        # "Inner" is a nested element (inside OuterType's particle) whose own
        # complexType is inline (not named) and carries an attribute — that
        # attribute is only reachable if iter_attributes recurses into a
        # nested element's own type_inline_complex, not just top-level ones.
        xsd = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="OuterType">
    <xs:sequence>
      <xs:element name="Inner">
        <xs:complexType>
          <xs:attribute name="innerAttr" type="xs:string"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>
  <xs:element name="Outer" type="OuterType"/>
</xs:schema>
"""
        model = parse_single(xsd, "nested-inline.xsd")
        names = {a.name for a in iter_attributes(model)}
        assert "innerAttr" in names
