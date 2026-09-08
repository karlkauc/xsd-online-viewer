"""Tests for backend/app/parser/idroles.py — ID/IDREF role classification."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.parser.idroles import expand_qname
from app.parser.model import ElementDecl, SchemaModel
from app.parser.walk import iter_attributes, iter_elements
from app.parser.xsd_parser import parse_files_map, parse_single

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent
FUNDSXML4_XSD = REPO_ROOT / "FundsXML4.xsd"


def _element_role(model: SchemaModel, name: str) -> str | None:
    return next(e.id_role for e in iter_elements(model) if e.name == name)


def _attribute_role(model: SchemaModel, name: str) -> str | None:
    return next(a.id_role for a in iter_attributes(model) if a.name == name)


class TestExpandQname:
    @pytest.mark.parametrize(
        ("qname", "namespaces", "expected"),
        [
            (
                "xs:ID",
                {"xs": "http://www.w3.org/2001/XMLSchema"},
                "{http://www.w3.org/2001/XMLSchema}ID",
            ),
            (
                "xsd:IDREF",
                {"xsd": "http://www.w3.org/2001/XMLSchema"},
                "{http://www.w3.org/2001/XMLSchema}IDREF",
            ),
            (
                "RefType",
                {"": "http://example.com/id-idref"},
                "{http://example.com/id-idref}RefType",
            ),
            ("RefType", {}, "RefType"),
            (
                "foo:ID",
                {"foo": "http://example.com/foo"},
                "{http://example.com/foo}ID",
            ),
            ("bar:ID", {}, "ID"),
        ],
    )
    def test_expand_qname(
        self, qname: str, namespaces: dict[str, str], expected: str
    ) -> None:
        assert expand_qname(qname, namespaces) == expected


class TestElementIdRoles:
    @pytest.fixture
    def model(self, id_idref_xsd_bytes: bytes) -> SchemaModel:
        return parse_single(id_idref_xsd_bytes, "id_idref.xsd")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("DirectId", "id"),
            ("DirectIdref", "idref"),
            ("DirectIdrefs", "idrefs"),
            ("PrefixedIdrefViaXsd", "idref"),
            ("NonXsdId", None),
            ("InlineIdrefRestriction", "idref"),
            ("QuirkInlineBaseIdref", "idref"),
            ("NamedRefTypeElement", "idref"),
            ("DerivedRefTypeElement", "idref"),
            ("ListOfRefType", "idrefs"),
            ("UnionRefOrToken", "idrefs"),
            ("UnionIdOrToken", "id"),
            ("CycleElement", None),
            ("SimpleContentIdElement", "id"),
            ("AttrHolder", None),
        ],
    )
    def test_element_role(
        self, model: SchemaModel, name: str, expected: str | None
    ) -> None:
        assert _element_role(model, name) == expected

    def test_element_with_ref_particle_stays_none(
        self, id_idref_xsd_bytes: bytes
    ) -> None:
        # Build a tiny schema with a ref particle pointing at a global
        # xs:ID-typed element: the ref particle itself must stay unroled —
        # the frontend resolves the role through resolveElementRef.
        xsd = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="http://example.com/ref"
           targetNamespace="http://example.com/ref"
           elementFormDefault="qualified">
  <xs:element name="GlobalId" type="xs:ID"/>
  <xs:complexType name="HolderType">
    <xs:sequence>
      <xs:element ref="tns:GlobalId"/>
    </xs:sequence>
  </xs:complexType>
  <xs:element name="Holder" type="tns:HolderType"/>
</xs:schema>
"""
        model = parse_single(xsd, "ref.xsd")
        ref_elements = [e for e in iter_elements(model) if e.ref is not None]
        assert len(ref_elements) == 1
        assert ref_elements[0].id_role is None


class TestAttributeIdRoles:
    @pytest.fixture
    def model(self, id_idref_xsd_bytes: bytes) -> SchemaModel:
        return parse_single(id_idref_xsd_bytes, "id_idref.xsd")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("id", "id"),
            ("namedRef", "idref"),
            ("inlineRef", "idref"),
            ("plain", None),
            ("globalIdAttr", "id"),
            ("groupRef", "idref"),
        ],
    )
    def test_attribute_role(
        self, model: SchemaModel, name: str, expected: str | None
    ) -> None:
        assert _attribute_role(model, name) == expected


class TestSimpleXsdFixture:
    def test_person_id_attribute_is_id(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        assert _attribute_role(model, "id") == "id"


class TestMultiFileNamedTypeNamespacing:
    """Named simple/complex types must be indexed under their *own* file's
    target namespace, not the model's primary one — otherwise a same-named
    type from an imported namespace collides with a main-namespace type of
    the same local name (regression: reviewer-reported in fix round 1)."""

    @pytest.fixture
    def model(self) -> SchemaModel:
        files = {
            name: (FIXTURES / name).read_bytes()
            for name in ("idroles-main.xsd", "idroles-other.xsd")
        }
        return parse_files_map(files, "idroles-main.xsd")

    def test_element_typed_by_imported_namespace_type_gets_its_role(
        self, model: SchemaModel
    ) -> None:
        # idroles-other.xsd's RefType (urn:idroles-other) restricts
        # xs:IDREF — must resolve via the Clark key scoped to *that* file's
        # namespace, not collide with idroles-main.xsd's own RefType.
        assert _element_role(model, "UseOther") == "idref"

    def test_element_typed_by_own_namespace_type_keeps_its_own_role(
        self, model: SchemaModel
    ) -> None:
        # idroles-main.xsd's RefType (urn:idroles-main) restricts xs:string
        # — must NOT pick up the "idref" role from the same-named imported
        # type.
        assert _element_role(model, "UseMain") is None


class TestDefaultIsNone:
    def test_plain_element_has_no_role_before_classification_would_apply(self) -> None:
        # Sanity check the field default independent of the classifier.
        element = ElementDecl(id="element:x", name="x")
        assert element.id_role is None


@pytest.mark.skipif(
    not FUNDSXML4_XSD.exists(),
    reason="FundsXML4.xsd is a local reference copy, not checked into git",
)
class TestFundsXML4:
    def test_id_and_idref_counts(self) -> None:
        content = FUNDSXML4_XSD.read_bytes()
        t0 = time.monotonic()
        model = parse_single(content, "FundsXML4.xsd")
        elapsed = time.monotonic() - t0
        assert elapsed < 5, f"parsing FundsXML4.xsd took {elapsed:.1f}s, expected < 5s"

        roles = [e.id_role for e in iter_elements(model)]
        assert roles.count("id") == 2
        assert roles.count("idref") == 10
        assert roles.count("idrefs") == 0
