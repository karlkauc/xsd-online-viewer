"""Tests for the XSD parser — correctness on small fixture schemas."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.parser.xsd_parser import parse_single, parse_zip

FIXTURES = Path(__file__).parent / "fixtures"


def _find_element(model, name):
    return next((e for e in model.elements if e.name == name), None)


def _find_complex(model, name):
    return next((t for t in model.complex_types if t.name == name), None)


def _find_simple(model, name):
    return next((t for t in model.simple_types if t.name == name), None)


class TestSimpleSchema:
    def test_top_level_elements(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        assert model.target_namespace == "http://example.com/simple"
        assert model.element_form_default == "qualified"
        person = _find_element(model, "Person")
        assert person is not None
        assert person.is_global
        assert person.type_name == "tns:PersonType"

    def test_complex_type_attributes(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        person_type = _find_complex(model, "PersonType")
        assert person_type is not None
        attr_names = {attr.name: attr for attr in person_type.attributes}
        assert attr_names["id"].use == "required"
        assert attr_names["id"].type_name == "xs:ID"
        assert attr_names["country"].default == "DE"

    def test_sequence_particles(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        person_type = _find_complex(model, "PersonType")
        assert person_type.particle is not None
        assert person_type.particle.kind == "sequence"
        child_names = [
            child.element.name
            for child in person_type.particle.children
            if child.element is not None
        ]
        assert child_names == ["FirstName", "LastName", "Age", "Email"]
        email = next(
            child for child in person_type.particle.children if child.element and child.element.name == "Email"
        )
        assert email.max_occurs == "unbounded"
        assert email.min_occurs == 0

    def test_simple_type_facets(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        age = _find_simple(model, "AgeType")
        assert age is not None
        assert age.derivation == "restriction"
        assert age.base == "xs:int"
        kinds = {facet.kind: facet.value for facet in age.facets}
        assert kinds == {"minInclusive": "0", "maxInclusive": "130"}

    def test_source_refs_present(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        for element in model.elements + model.complex_types + model.simple_types:
            assert element.source_ref is not None
            assert element.source_ref.line is not None
            assert element.source_ref.line > 0


class TestAnnotations:
    def test_multi_language_documentation(self, annotated_xsd_bytes: bytes) -> None:
        model = parse_single(annotated_xsd_bytes, "annotated.xsd")
        color = _find_simple(model, "ColorType")
        assert color.annotation is not None
        langs = {doc.lang for doc in color.annotation.documentation}
        assert {"en", "de"} <= langs

    def test_preceding_comment_captured(self, annotated_xsd_bytes: bytes) -> None:
        model = parse_single(annotated_xsd_bytes, "annotated.xsd")
        color = _find_simple(model, "ColorType")
        assert color.annotation is not None
        assert any(
            "describing ColorType" in comment for comment in color.annotation.comments
        )

    def test_enumeration_facets(self, annotated_xsd_bytes: bytes) -> None:
        model = parse_single(annotated_xsd_bytes, "annotated.xsd")
        color = _find_simple(model, "ColorType")
        values = {facet.value for facet in color.facets if facet.kind == "enumeration"}
        assert values == {"red", "green", "blue"}

    def test_inline_types_attached_to_element(self, annotated_xsd_bytes: bytes) -> None:
        model = parse_single(annotated_xsd_bytes, "annotated.xsd")
        widget = _find_element(model, "Widget")
        assert widget is not None
        assert widget.type_inline_complex is not None
        assert widget.type_inline_complex.particle is not None
        size = next(
            p
            for p in widget.type_inline_complex.particle.children
            if p.element and p.element.name == "Size"
        )
        assert size.element.type_inline_simple is not None
        assert size.element.type_inline_simple.base == "xs:int"


class TestIncludeResolution:
    def test_zip_include_resolved(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(FIXTURES / "library.xsd", "library.xsd")
            archive.write(FIXTURES / "types.xsd", "types.xsd")
        model = parse_zip(buffer.getvalue(), main_filename="library.xsd")
        filenames = {f.filename for f in model.files}
        assert "library.xsd" in filenames
        assert "types.xsd" in filenames
        # ISBNType from types.xsd must be visible as a simple type
        assert _find_simple(model, "ISBNType") is not None

    def test_missing_include_is_reported(self, library_xsd_bytes: bytes) -> None:
        # Single-file parse of library.xsd cannot find types.xsd — must emit a warning
        model = parse_single(library_xsd_bytes, "library.xsd")
        warnings = [d for d in model.diagnostics if d.severity == "warning"]
        assert any("unresolved" in d.message for d in warnings)
