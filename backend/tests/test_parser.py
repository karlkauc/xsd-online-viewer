"""Tests for the XSD parser — correctness on small fixture schemas."""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from app.parser.sample import generate_sample
from app.parser.validation import unloaded_files, validate_xml
from app.parser.walk import iter_elements
from app.parser.xsd_parser import parse_files_map, parse_single, parse_zip

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent
FUNDSXML4_XSD = REPO_ROOT / "FundsXML4.xsd"


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
            child
            for child in person_type.particle.children
            if child.element and child.element.name == "Email"
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

    def test_nested_elements_have_own_source_ref_lines(
        self, simple_xsd_bytes: bytes
    ) -> None:
        # simple.xsd layout (see fixtures/simple.xsd):
        #   9: <xs:complexType name="PersonType">
        #  11: <xs:element name="FirstName" ...
        #  12: <xs:element name="LastName" ...
        #  13: <xs:element name="Age" ...
        #  14: <xs:element name="Email" ...
        # Each nested element must carry its OWN source line, not the
        # enclosing complexType's line.
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        person_type = _find_complex(model, "PersonType")
        by_name = {
            child.element.name: child.element
            for child in person_type.particle.children
            if child.element is not None
        }
        assert by_name["FirstName"].source_ref.line == 11
        assert by_name["LastName"].source_ref.line == 12
        assert by_name["Age"].source_ref.line == 13
        assert by_name["Email"].source_ref.line == 14

    def test_nested_attributes_have_own_source_ref_lines(
        self, simple_xsd_bytes: bytes
    ) -> None:
        # simple.xsd:
        #  16: <xs:attribute name="id" ...
        #  17: <xs:attribute name="country" ...
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        person_type = _find_complex(model, "PersonType")
        by_name = {attr.name: attr for attr in person_type.attributes}
        assert by_name["id"].source_ref.line == 16
        assert by_name["country"].source_ref.line == 17


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


class TestXsd11Infrastructure:
    def test_version_detected_via_vc_attribute(
        self, vc_versioning_xsd_bytes: bytes
    ) -> None:
        model = parse_single(vc_versioning_xsd_bytes, "vc-versioning.xsd")
        assert model.xsd_version == "1.1"

    def test_schema_level_xsd_11_attributes_propagate(
        self, vc_versioning_xsd_bytes: bytes
    ) -> None:
        model = parse_single(vc_versioning_xsd_bytes, "vc-versioning.xsd")
        assert model.xpath_default_namespace == "http://example.com/vc"
        assert model.default_attributes == "tns:CommonAttrs"
        assert model.default_open_content is None  # populated in Phase 4

    def test_version_constraints_on_element(
        self, vc_versioning_xsd_bytes: bytes
    ) -> None:
        model = parse_single(vc_versioning_xsd_bytes, "vc-versioning.xsd")
        event = _find_element(model, "Event")
        assert event is not None
        assert event.version_constraints is not None
        assert event.version_constraints.type_available == "xs:dateTimeStamp"

    def test_version_constraints_on_complex_and_simple_type(
        self, vc_versioning_xsd_bytes: bytes
    ) -> None:
        model = parse_single(vc_versioning_xsd_bytes, "vc-versioning.xsd")
        event_type = _find_complex(model, "EventType")
        assert event_type is not None
        assert event_type.version_constraints is not None
        assert event_type.version_constraints.max_version == "2.0"

        # vc:maxVersion="1.1" is exclusive: an XSD 1.1 processor does not see it.
        assert _find_simple(model, "LegacyToken") is None
        (warning,) = model.diagnostics
        assert "1 declaration was left out by vc:* conditions" in warning.message
        assert warning.line == 25

    def test_legacy_schema_reports_version_1_0(self, simple_xsd_bytes: bytes) -> None:
        # simple.xsd uses no XSD 1.1 constructs and no vc:* attributes.
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        assert model.xsd_version == "1.0"
        assert model.xpath_default_namespace is None
        assert model.default_attributes is None
        for element in model.elements + model.complex_types + model.simple_types:
            assert element.version_constraints is None


class TestXsd11Assertions:
    def test_complex_assertions_collected(self, assertions_xsd_bytes: bytes) -> None:
        model = parse_single(assertions_xsd_bytes, "assertions.xsd")
        date_range = _find_complex(model, "DateRange")
        assert date_range is not None
        assert len(date_range.assertions) == 3
        tests = [a.test for a in date_range.assertions]
        assert tests[0] == "xs:date(From) le xs:date(To)"
        assert tests[1].endswith("le current-date()")

    def test_assertion_xpath_default_namespace_captured(
        self, assertions_xsd_bytes: bytes
    ) -> None:
        model = parse_single(assertions_xsd_bytes, "assertions.xsd")
        date_range = _find_complex(model, "DateRange")
        second = date_range.assertions[1]
        assert second.xpath_default_namespace == "http://example.com/assert"
        assert second.annotation is not None
        assert second.annotation.documentation
        assert "future" in second.annotation.documentation[0].text

    def test_assertion_version_constraints_propagate(
        self, assertions_xsd_bytes: bytes
    ) -> None:
        model = parse_single(assertions_xsd_bytes, "assertions.xsd")
        date_range = _find_complex(model, "DateRange")
        third = date_range.assertions[2]
        assert third.version_constraints is not None
        assert third.version_constraints.min_version == "1.1"

    def test_simple_type_assertion_lifted_out_of_facets(
        self, assertions_xsd_bytes: bytes
    ) -> None:
        model = parse_single(assertions_xsd_bytes, "assertions.xsd")
        even = _find_simple(model, "EvenInt")
        assert even is not None
        # The 1.0-style minInclusive facet stays in facets[]; the 1.1
        # xs:assertion is promoted to assertions[] and removed from facets.
        facet_kinds = {f.kind for f in even.facets}
        assert "assertion" not in facet_kinds
        assert "minInclusive" in facet_kinds
        assert len(even.assertions) == 1
        assert even.assertions[0].test == "$value mod 2 eq 0"

    def test_assertion_source_lines_captured(
        self, assertions_xsd_bytes: bytes
    ) -> None:
        model = parse_single(assertions_xsd_bytes, "assertions.xsd")
        date_range = _find_complex(model, "DateRange")
        for a in date_range.assertions:
            assert a.source_ref is not None
            assert a.source_ref.line is not None
            assert a.source_ref.line > 0

    def test_legacy_simple_xsd_has_no_assertions(self, simple_xsd_bytes: bytes) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        for t in model.simple_types:
            assert t.assertions == []
        for t in model.complex_types:
            assert t.assertions == []


class TestXsd11Alternatives:
    def test_three_alternatives_collected_in_order(
        self, alternatives_xsd_bytes: bytes
    ) -> None:
        model = parse_single(alternatives_xsd_bytes, "alternatives.xsd")
        pet = _find_element(model, "Pet")
        assert pet is not None
        assert len(pet.alternatives) == 3
        tests = [alt.test for alt in pet.alternatives]
        assert tests[0] == "@kind = 'dog'"
        assert tests[1] == "@kind = 'cat'"
        assert tests[2] is None  # default branch — no `test` attribute

    def test_alternative_named_and_inline_types(
        self, alternatives_xsd_bytes: bytes
    ) -> None:
        model = parse_single(alternatives_xsd_bytes, "alternatives.xsd")
        pet = _find_element(model, "Pet")
        first, second, third = pet.alternatives
        assert first.type_name == "tns:Dog"
        assert first.type_inline_complex is None

        # Inline complex: anonymous extension of Animal with Indoor element.
        assert second.type_name is None
        assert second.type_inline_complex is not None
        assert second.type_inline_complex.derivation == "extension"

        # Default branch falls back to a named type.
        assert third.type_name == "tns:Animal"
        assert third.type_inline_complex is None

    def test_alternative_xpath_default_namespace_and_vc(
        self, alternatives_xsd_bytes: bytes
    ) -> None:
        model = parse_single(alternatives_xsd_bytes, "alternatives.xsd")
        pet = _find_element(model, "Pet")
        first, second, third = pet.alternatives
        assert first.xpath_default_namespace is None
        assert second.xpath_default_namespace == "http://example.com/alt"
        assert third.version_constraints is not None
        assert third.version_constraints.min_version == "1.1"

    def test_alternative_source_lines(self, alternatives_xsd_bytes: bytes) -> None:
        model = parse_single(alternatives_xsd_bytes, "alternatives.xsd")
        pet = _find_element(model, "Pet")
        for alt in pet.alternatives:
            assert alt.source_ref is not None
            assert alt.source_ref.line is not None
            assert alt.source_ref.line > 0

    def test_legacy_simple_xsd_has_no_alternatives(
        self, simple_xsd_bytes: bytes
    ) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        for el in model.elements:
            assert el.alternatives == []


class TestXsd11OpenContent:
    def test_default_open_content_propagates_to_schema(
        self, open_content_xsd_bytes: bytes
    ) -> None:
        model = parse_single(open_content_xsd_bytes, "open-content.xsd")
        assert model.default_open_content is not None
        doc = model.default_open_content
        assert doc.mode == "interleave"  # default when @mode is omitted
        assert doc.applies_to_empty is True
        assert doc.wildcard is not None
        assert doc.wildcard.namespace == "##other"
        assert doc.wildcard.process_contents == "lax"

    def test_complex_inherits_default_open_content(
        self, open_content_xsd_bytes: bytes
    ) -> None:
        model = parse_single(open_content_xsd_bytes, "open-content.xsd")
        a = _find_complex(model, "A")
        assert a is not None and a.open_content is not None
        assert a.open_content.origin == "default"
        assert a.open_content.wildcard.namespace == "##other"
        assert _find_complex(model, "B").open_content.origin == "own"

    def test_complex_with_suffix_open_content(
        self, open_content_xsd_bytes: bytes
    ) -> None:
        model = parse_single(open_content_xsd_bytes, "open-content.xsd")
        b = _find_complex(model, "B")
        assert b.open_content is not None
        assert b.open_content.mode == "suffix"
        assert b.open_content.wildcard is not None
        assert b.open_content.wildcard.namespace == "##any"
        assert b.open_content.wildcard.process_contents == "skip"

    def test_complex_with_open_content_none_opts_out(
        self, open_content_xsd_bytes: bytes
    ) -> None:
        model = parse_single(open_content_xsd_bytes, "open-content.xsd")
        c = _find_complex(model, "C")
        assert c.open_content is not None
        assert c.open_content.mode == "none"
        # mode="none" has no wildcard child; absence is OK.
        assert c.open_content.wildcard is None

    def test_open_content_source_lines(
        self, open_content_xsd_bytes: bytes
    ) -> None:
        model = parse_single(open_content_xsd_bytes, "open-content.xsd")
        b = _find_complex(model, "B")
        assert b.open_content is not None
        assert b.open_content.source_ref is not None
        assert b.open_content.source_ref.line is not None

    def test_legacy_simple_xsd_has_no_open_content(
        self, simple_xsd_bytes: bytes
    ) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        assert model.default_open_content is None
        for ct in model.complex_types:
            assert ct.open_content is None


class TestXsd11InheritableAllDefaultAttrs:
    def test_inheritable_attribute_flag(
        self, inheritable_and_all_xsd_bytes: bytes
    ) -> None:
        model = parse_single(
            inheritable_and_all_xsd_bytes, "inheritable-and-all.xsd"
        )
        doc = _find_complex(model, "Document")
        assert doc is not None
        by_name = {a.name: a for a in doc.attributes}
        assert by_name["security"].inheritable is True

    def test_legacy_attribute_is_not_inheritable(
        self, simple_xsd_bytes: bytes
    ) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        person = _find_complex(model, "PersonType")
        for a in person.attributes:
            assert a.inheritable is False

    def test_xs_all_with_max_occurs_and_wildcard_parses(
        self, inheritable_and_all_xsd_bytes: bytes
    ) -> None:
        model = parse_single(
            inheritable_and_all_xsd_bytes, "inheritable-and-all.xsd"
        )
        bag = _find_complex(model, "Bag")
        assert bag is not None
        assert bag.particle is not None
        assert bag.particle.kind == "all"
        assert bag.particle.max_occurs == 3
        kinds = [c.kind for c in bag.particle.children]
        assert "any" in kinds  # XSD 1.1 allows xs:any inside xs:all

    def test_default_attributes_propagates_to_schema(
        self, inheritable_and_all_xsd_bytes: bytes
    ) -> None:
        model = parse_single(
            inheritable_and_all_xsd_bytes, "inheritable-and-all.xsd"
        )
        assert model.default_attributes == "tns:CommonAttrs"

    def test_default_attributes_apply_defaults_to_true(
        self, inheritable_and_all_xsd_bytes: bytes
    ) -> None:
        model = parse_single(
            inheritable_and_all_xsd_bytes, "inheritable-and-all.xsd"
        )
        doc = _find_complex(model, "Document")
        assert doc.default_attributes_apply is True

    def test_default_attributes_apply_false_when_opted_out(
        self, inheritable_and_all_xsd_bytes: bytes
    ) -> None:
        model = parse_single(
            inheritable_and_all_xsd_bytes, "inheritable-and-all.xsd"
        )
        plain = _find_complex(model, "Plain")
        assert plain.default_attributes_apply is False


class TestXsd11Override:
    def _parse_pair(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ):
        return parse_files_map(
            {
                "override.xsd": override_xsd_bytes,
                "override-base.xsd": override_base_xsd_bytes,
            },
            main_filename="override.xsd",
        )

    def test_the_replacement_takes_the_originals_place(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        (color,) = [c for c in model.complex_types if c.name == "ColorType"]
        assert color.id == "complexType:{http://example.com/ovr}ColorType"
        assert [c.element.name for c in color.particle.children] == ["C", "M", "Y", "K"]
        # What the overridden file declares besides is untouched.
        assert _find_element(model, "OriginalOnly") is not None

    def test_override_directive_records_replacements(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        (directive,) = model.overrides
        base = next(f for f in model.files if f.filename == "override-base.xsd")
        assert directive.target_file_id == base.id
        (replacement,) = directive.replacements
        assert replacement.kind == "complexType"
        assert replacement.replacement_id == "complexType:{http://example.com/ovr}ColorType"
        assert replacement.source_ref.line == 9
        # Where the definition it replaced is written, for the Text view.
        assert (replacement.original_source_ref.file_id, replacement.original_source_ref.line) == (
            base.id,
            7,
        )

    def test_an_override_cannot_add_a_component(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        """XSD 1.1, 4.2.5: what matches nothing in the overridden file is dropped."""
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        assert _find_element(model, "AddedByOverride") is None
        (warning,) = model.diagnostics
        assert "xs:override of element 'AddedByOverride'" in warning.message
        assert "ignored" in warning.message

    def test_an_overridden_element_and_references_to_it(self) -> None:
        xs = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        model = parse_files_map(
            {
                "main.xsd": (
                    f'<xs:schema {xs}><xs:override schemaLocation="base.xsd">'
                    '<xs:element name="Id" type="xs:int"/>'
                    '<xs:simpleType name="Code"><xs:restriction base="xs:token"/></xs:simpleType>'
                    "</xs:override></xs:schema>"
                ).encode(),
                "base.xsd": (
                    f'<xs:schema {xs}><xs:element name="Id" type="xs:string"/>'
                    '<xs:simpleType name="Code"><xs:restriction base="xs:string"/></xs:simpleType>'
                    '<xs:element name="Doc"><xs:complexType><xs:sequence>'
                    '<xs:element ref="Id"/><xs:element name="C" type="Code"/>'
                    "</xs:sequence></xs:complexType></xs:element></xs:schema>"
                ).encode(),
            },
            main_filename="main.xsd",
        )
        assert model.diagnostics == []
        # One declaration each, in the original's position, and the reference reaches it.
        assert [(e.name, e.type_name) for e in model.elements] == [("Id", "xs:int"), ("Doc", None)]
        assert [(t.name, t.base) for t in model.simple_types] == [("Code", "xs:token")]
        doc = _find_element(model, "Doc")
        assert doc.type_inline_complex.particle.children[0].element.ref_id == "element:Id"

    def test_override_target_file_loaded_with_relationship_override(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        rels = {f.filename: f.relationship for f in model.files}
        assert rels.get("override-base.xsd") == "override"

    def test_legacy_simple_xsd_has_no_overrides(
        self, simple_xsd_bytes: bytes
    ) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        assert model.overrides == []


    def test_a_replacement_is_read_under_the_overridden_files_defaults(self) -> None:
        """An override transforms the overridden document, so its defaultAttributes,
        blockDefault and target namespace apply, not those of the file the block is in."""
        xs = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        model = parse_files_map(
            {
                "main.xsd": (
                    f'<xs:schema {xs}><xs:override schemaLocation="base.xsd">'
                    '<xs:complexType name="T"><xs:sequence><xs:element name="b"/></xs:sequence>'
                    "</xs:complexType></xs:override></xs:schema>"
                ).encode(),
                "base.xsd": (
                    f'<xs:schema {xs} targetNamespace="urn:base" xmlns="urn:base" '
                    'defaultAttributes="Common" blockDefault="extension">'
                    '<xs:defaultOpenContent><xs:any processContents="skip"/></xs:defaultOpenContent>'
                    '<xs:attributeGroup name="Common"><xs:attribute name="lang"/></xs:attributeGroup>'
                    '<xs:complexType name="T"><xs:sequence><xs:element name="a"/></xs:sequence>'
                    "</xs:complexType></xs:schema>"
                ).encode(),
            },
            main_filename="main.xsd",
        )
        (t,) = model.complex_types
        assert t.id == "complexType:{urn:base}T"
        assert [c.element.name for c in t.particle.children] == ["b"]
        assert (t.default_attributes, t.block, t.open_content.origin) == (
            "Common",
            ["extension"],
            "default",
        )
        main = next(f for f in model.files if f.relationship == "main")
        assert t.source_ref.file_id == main.id  # still where it is written


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

    @pytest.mark.parametrize(
        ("stored_as", "location"),
        [
            ("base/types.xsd", "..\\base\\types.xsd"),  # authored on Windows
            ("base/my types.xsd", "../base/my%20types.xsd"),  # a schemaLocation is a URI
            ("types.xsd", "shared/types.xsd"),  # loose files, uploaded without folders
        ],
        ids=["backslash", "percent-encoded", "bare-name"],
    )
    def test_include_location_spellings(self, stored_as: str, location: str) -> None:
        files = {
            "main/main.xsd": (
                '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
                f'<xs:include schemaLocation="{location}"/>'
                '<xs:element name="root" type="T"/></xs:schema>'
            ).encode(),
            stored_as: (
                b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
                b'<xs:simpleType name="T"><xs:restriction base="xs:string"/></xs:simpleType>'
                b"</xs:schema>"
            ),
        }
        model = parse_files_map(files, "main/main.xsd")
        assert _find_simple(model, "T") is not None
        assert not model.diagnostics
        # libxml2 reads the location as written; the validator has to bridge that.
        assert validate_xml(model, b"<root>x</root>").is_valid

    def test_same_named_file_in_another_folder_is_not_a_match(self) -> None:
        files = {
            "main.xsd": (
                b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
                b'<xs:include schemaLocation="a/types.xsd"/></xs:schema>'
            ),
            "b/types.xsd": b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>',
        }
        model = parse_files_map(files, "main.xsd")
        assert [d.message for d in model.diagnostics] == [
            "main.xsd: unresolved include schemaLocation='a/types.xsd'"
        ]

    def test_unresolved_windows_location_is_named_as_written(self) -> None:
        model = parse_single(
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            b'<xs:include schemaLocation="..\\LetterBase.xsd"/></xs:schema>',
            "letter.xsd",
        )
        assert model.diagnostics[0].message.endswith("schemaLocation='..\\LetterBase.xsd'")
        assert unloaded_files(model) == ["..\\LetterBase.xsd"]

    def test_missing_include_is_reported(self, library_xsd_bytes: bytes) -> None:
        # Single-file parse of library.xsd cannot find types.xsd — must emit a warning
        model = parse_single(library_xsd_bytes, "library.xsd")
        warnings = [d for d in model.diagnostics if d.severity == "warning"]
        assert any("unresolved" in d.message for d in warnings)


class TestElementRefResolution:
    """``<xs:element ref="...">`` particles must point at the global
    declaration they reference — including across an ``xs:import`` (e.g.
    ``ds:Signature`` from xmldsig-core behind FundsXML)."""

    @staticmethod
    def _host_model():
        files = {
            name: (FIXTURES / name).read_bytes()
            for name in ("imports-dsig.xsd", "xmldsig-core-schema.xsd")
        }
        return parse_files_map(files, "imports-dsig.xsd")

    @staticmethod
    def _particles(model):
        document = _find_element(model, "Document")
        assert document is not None
        assert document.type_inline_complex is not None
        assert document.type_inline_complex.particle is not None
        return document.type_inline_complex.particle.children

    def test_imported_ref_points_at_global_declaration(self) -> None:
        model = self._host_model()
        signature = next(
            p.element for p in self._particles(model) if p.element.ref == "ds:Signature"
        )
        assert signature.ref_id == (
            "element:{http://www.w3.org/2000/09/xmldsig#}Signature"
        )
        assert signature.ref_id in {e.id for e in model.elements}

    def test_same_namespace_ref_points_at_global_declaration(self) -> None:
        model = self._host_model()
        footer = next(
            p.element for p in self._particles(model) if p.element.ref == "tns:Footer"
        )
        assert footer.ref_id == "element:{http://example.com/host}Footer"
        assert footer.ref_id in {e.id for e in model.elements}

    def test_named_declarations_have_no_ref_id(self) -> None:
        model = self._host_model()
        body = next(p.element for p in self._particles(model) if p.element.name == "Body")
        assert body.ref_id is None
        assert _find_element(model, "Footer").ref_id is None


class TestPickMainXsd:
    def test_names_only_prefers_shallow_then_short(self) -> None:
        from app.parser.xsd_parser import pick_main_xsd

        assert pick_main_xsd(["x/deep.xsd", "main-schema.xsd", "a.xsd", "readme.txt"]) == "a.xsd"
        assert pick_main_xsd(["readme.txt"]) is None

    def test_contents_prefer_the_unreferenced_root(self) -> None:
        from app.parser.xsd_parser import pick_main_xsd

        files = {
            "types.xsd": b"<xs:schema/>",
            "library.xsd": b'<xs:schema><xs:include schemaLocation="types.xsd"/></xs:schema>',
        }
        assert pick_main_xsd(files) == "library.xsd"

    def test_contents_resolve_relative_locations(self) -> None:
        from app.parser.xsd_parser import pick_main_xsd

        files = {
            "schemas/common/types.xsd": b"<xs:schema/>",
            "schemas/main.xsd": b'<xs:schema><xs:import schemaLocation="./common/types.xsd"/></xs:schema>',
        }
        assert pick_main_xsd(files) == "schemas/main.xsd"


class TestLeadingWhitespaceBeforeXmlDeclaration:
    """Some published schemas (e.g. nuspec.xsd on GitHub) start with a blank
    line before ``<?xml ...?>``. The XML spec forbids that, but the viewer
    should still load the file and tell the user about the defect."""

    def test_is_parsed_with_a_warning(self, library_xsd_bytes: bytes) -> None:
        assert library_xsd_bytes.startswith(b"<?xml")
        content = b"\n  \n" + library_xsd_bytes
        model = parse_single(content, "library.xsd")
        assert _find_element(model, "Library") is not None
        warnings = [d for d in model.diagnostics if d.severity == "warning"]
        assert any("XML declaration" in d.message and "whitespace" in d.message for d in warnings)

    def test_stripped_content_is_kept_for_the_text_view(self, library_xsd_bytes: bytes) -> None:
        model = parse_single(b"\n" + library_xsd_bytes, "library.xsd")
        (main,) = [f for f in model.files if f.filename == "library.xsd"]
        assert main.content.startswith("<?xml")


def _find_by_name(model, name: str):
    """Best-effort: the first element anywhere in the model (top-level or
    nested in a content model) with this name."""
    return next((e for e in iter_elements(model) if e.name == name), None)


class TestIdentityConstraints:
    def test_document_order(self, identity_constraints_xsd_bytes: bytes) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        assert library is not None
        names = [c.name for c in library.identity_constraints]
        assert names == ["bookKey", "uniqueTitle", "loanBookRef", "danglingRef"]

    def test_kinds(self, identity_constraints_xsd_bytes: bytes) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        kinds = {c.name: c.kind for c in library.identity_constraints}
        assert kinds == {
            "bookKey": "key",
            "uniqueTitle": "unique",
            "loanBookRef": "keyref",
            "danglingRef": "keyref",
        }

    def test_selector_and_fields_verbatim(
        self, identity_constraints_xsd_bytes: bytes
    ) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        by_name = {c.name: c for c in library.identity_constraints}
        assert by_name["bookKey"].selector == "tns:Books/tns:Book"
        assert by_name["bookKey"].fields == ["tns:ISBN"]
        assert by_name["uniqueTitle"].selector == ".//tns:Book"
        assert by_name["uniqueTitle"].fields == ["@title", "tns:Edition"]

    def test_id_and_qname_are_clark_form(
        self, identity_constraints_xsd_bytes: bytes
    ) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        book_key = next(c for c in library.identity_constraints if c.name == "bookKey")
        assert book_key.qname == "{http://example.com/keys}bookKey"
        assert book_key.id == "identityConstraint:{http://example.com/keys}bookKey"

    def test_keyref_resolves_refer_id_to_the_key(
        self, identity_constraints_xsd_bytes: bytes
    ) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        by_name = {c.name: c for c in library.identity_constraints}
        book_key = by_name["bookKey"]
        loan_book_ref = by_name["loanBookRef"]
        assert loan_book_ref.refer == "tns:bookKey"
        assert loan_book_ref.refer_id == book_key.id

    def test_dangling_keyref_gets_no_refer_id_and_a_warning(
        self, identity_constraints_xsd_bytes: bytes
    ) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        dangling = next(c for c in library.identity_constraints if c.name == "danglingRef")
        assert dangling.refer == "tns:noSuchKey"
        assert dangling.refer_id is None
        warnings = [d for d in model.diagnostics if d.severity == "warning"]
        assert any(
            "danglingRef" in d.message and "noSuchKey" in d.message for d in warnings
        )

    def test_annotation_source_line_and_version_constraints(
        self, identity_constraints_xsd_bytes: bytes
    ) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        library = _find_element(model, "Library")
        by_name = {c.name: c for c in library.identity_constraints}

        book_key = by_name["bookKey"]
        assert book_key.annotation is not None
        assert book_key.annotation.documentation
        assert "unique among the library's books" in book_key.annotation.documentation[0].text
        assert book_key.source_ref is not None
        assert book_key.source_ref.line is not None
        assert book_key.source_ref.line > 0

        loan_book_ref = by_name["loanBookRef"]
        assert loan_book_ref.version_constraints is not None
        assert loan_book_ref.version_constraints.min_version == "1.1"

    def test_nested_element_has_its_own_constraint(
        self, identity_constraints_xsd_bytes: bytes
    ) -> None:
        model = parse_single(identity_constraints_xsd_bytes, "identity_constraints.xsd")
        loans = _find_by_name(model, "Loans")
        assert loans is not None
        assert [c.name for c in loans.identity_constraints] == ["loanKey"]
        assert loans.identity_constraints[0].kind == "key"

    def test_unprefixed_refer_without_target_namespace(self) -> None:
        # Mirrors FundsXML4.xsd (no targetNamespace, no tns prefix): Fund's
        # "benchmarkID" key and "benchmarkDynamicRef" keyref, whose `refer`
        # attribute is a bare local name.
        xsd = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="FundType">
    <xs:sequence>
      <xs:element name="BenchmarkID" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>
  <xs:element name="Funds">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Fund" type="FundType" maxOccurs="unbounded">
          <xs:key name="benchmarkID">
            <xs:selector xpath="FundStaticData/Benchmarks/Benchmark"/>
            <xs:field xpath="BenchmarkID"/>
          </xs:key>
          <xs:keyref name="benchmarkDynamicRef" refer="benchmarkID">
            <xs:selector xpath="FundDynamicData/Benchmarks/Benchmark"/>
            <xs:field xpath="BenchmarkID"/>
          </xs:keyref>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""
        model = parse_single(xsd, "fundsxml-like.xsd")
        fund = _find_by_name(model, "Fund")
        assert fund is not None
        by_name = {c.name: c for c in fund.identity_constraints}
        assert by_name["benchmarkID"].id == "identityConstraint:benchmarkID"
        assert by_name["benchmarkID"].qname == "benchmarkID"
        assert by_name["benchmarkDynamicRef"].refer_id == "identityConstraint:benchmarkID"
        assert model.diagnostics == []

    def test_legacy_simple_xsd_has_no_identity_constraints(
        self, simple_xsd_bytes: bytes
    ) -> None:
        model = parse_single(simple_xsd_bytes, "simple.xsd")
        for el in model.elements:
            assert el.identity_constraints == []

    def test_missing_selector_defaults_to_empty_string(self) -> None:
        xsd = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Broken">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="A" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
    <xs:key name="noSelector">
      <xs:field xpath="A"/>
    </xs:key>
  </xs:element>
</xs:schema>"""
        model = parse_single(xsd, "broken.xsd")
        broken = _find_element(model, "Broken")
        assert broken is not None
        (constraint,) = broken.identity_constraints
        assert constraint.selector == ""
        assert constraint.fields == ["A"]

    def test_keyref_without_refer_does_not_crash_or_warn(self) -> None:
        xsd = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Broken">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="A" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
    <xs:keyref name="noRefer">
      <xs:selector xpath="."/>
      <xs:field xpath="A"/>
    </xs:keyref>
  </xs:element>
</xs:schema>"""
        model = parse_single(xsd, "broken.xsd")
        broken = _find_element(model, "Broken")
        assert broken is not None
        (constraint,) = broken.identity_constraints
        assert constraint.refer is None
        assert constraint.refer_id is None
        assert model.diagnostics == []

    def test_xsd11_key_ref_falls_back_to_local_name(self) -> None:
        # XSD 1.1 identity-constraint sharing: <xs:key ref="..."> reuses
        # another constraint's fields instead of declaring its own; it has
        # no `name` of its own, so we fall back to the ref's local part for
        # display.
        xsd = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="http://example.com/keyref"
           targetNamespace="http://example.com/keyref">
  <xs:element name="Outer">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Inner" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
    <xs:key name="outerKey">
      <xs:selector xpath="."/>
      <xs:field xpath="tns:Inner"/>
    </xs:key>
  </xs:element>
  <xs:element name="Sibling">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Inner" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
    <xs:key ref="tns:outerKey"/>
  </xs:element>
</xs:schema>"""
        model = parse_single(xsd, "keyref-share.xsd")
        sibling = _find_element(model, "Sibling")
        assert sibling is not None
        (constraint,) = sibling.identity_constraints
        assert constraint.name == "outerKey"
        assert constraint.selector == ""
        assert constraint.fields == []

    @pytest.mark.skipif(
        not FUNDSXML4_XSD.exists(),
        reason="FundsXML4.xsd is a local reference copy, not checked into git",
    )
    def test_fundsxml4_key_and_keyref_are_parsed(self) -> None:
        content = FUNDSXML4_XSD.read_bytes()
        t0 = time.monotonic()
        model = parse_single(content, "FundsXML4.xsd")
        elapsed = time.monotonic() - t0
        assert elapsed < 5, f"parsing FundsXML4.xsd took {elapsed:.1f}s, expected < 5s"

        fund = _find_by_name(model, "Fund")
        assert fund is not None
        by_name = {c.name: c for c in fund.identity_constraints}
        assert by_name["benchmarkID"].kind == "key"
        assert by_name["benchmarkID"].selector == "FundStaticData/Benchmarks/Benchmark"
        keyref = by_name["benchmarkDynamicRef"]
        assert keyref.kind == "keyref"
        assert keyref.refer == "benchmarkID"
        assert keyref.refer_id == by_name["benchmarkID"].id

        transactions = _find_by_name(model, "Transactions")
        assert transactions is not None
        assert [c.name for c in transactions.identity_constraints] == ["transactionID"]

        # No dangling keyrefs anywhere in the real-world schema.
        assert not any("unknown key" in d.message for d in model.diagnostics)


class TestAttributeWhitespace:
    """Enumerated and QName attributes collapse whitespace (xs:token); lxml does not."""

    PADDED = b"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
        elementFormDefault="qualified " attributeFormDefault=" unqualified">
      <xs:complexType name=" T ">
        <xs:sequence>
          <xs:element name="a" type=" xs:string " form=" qualified" nillable="true "
                      minOccurs=" 0" maxOccurs="unbounded "/>
          <xs:any processContents="lax " minOccurs="unbounded"/>
        </xs:sequence>
        <xs:attribute name="x" type="xs:int" use="required " form="unqualified "/>
      </xs:complexType>
      <xs:element name="root" type=" T"/>
    </xs:schema>"""

    def test_padded_values_load_as_written_without_the_padding(self) -> None:
        model = parse_single(self.PADDED, "padded.xsd")
        assert model.element_form_default == "qualified"
        assert model.attribute_form_default == "unqualified"
        assert _find_element(model, "root").type_name == "T"

        complex_type = _find_complex(model, "T")
        assert complex_type is not None
        child_particle, wildcard = complex_type.particle.children
        child = child_particle.element
        assert (child.type_name, child.form, child.nillable) == ("xs:string", "qualified", True)
        assert (child.min_occurs, child.max_occurs) == (0, "unbounded")
        assert wildcard.wildcard_process_contents == "lax"
        assert wildcard.min_occurs == 1  # "unbounded" is no minOccurs
        attribute = complex_type.attributes[0]
        assert (attribute.use, attribute.form) == ("required", "unqualified")

    def test_unknown_enumerated_value_reads_as_absent(self) -> None:
        xsd = self.PADDED.replace(b'"qualified "', b'"sometimes"').replace(b'"lax "', b'"maybe"')
        model = parse_single(xsd, "odd.xsd")
        assert model.element_form_default == "unqualified"
        wildcard = _find_complex(model, "T").particle.children[1]
        assert wildcard.wildcard_process_contents is None


class TestRedefine:
    @pytest.fixture
    def model(self, redefine_xsd_bytes: bytes, redefine_base_xsd_bytes: bytes):
        return parse_files_map(
            {"redefine.xsd": redefine_xsd_bytes, "redefine-base.xsd": redefine_base_xsd_bytes},
            main_filename="redefine.xsd",
        )

    def test_redefinition_takes_the_name_and_derives_from_the_original(self, model) -> None:
        person = _find_complex(model, "PersonType")
        assert person.id == "complexType:{urn:redefine}PersonType"
        assert person.derivation == "extension"
        assert person.base == "t:PersonType~original"
        original = _find_complex(model, "PersonType~original")
        assert original.id == "complexType:{urn:redefine}PersonType~original"
        assert [p.element.name for p in original.particle.children] == ["name"]
        assert len([c for c in model.complex_types if c.name == "PersonType"]) == 1

    def test_reference_inside_the_redefinition_means_the_redefinition(self, model) -> None:
        partner = _find_complex(model, "PersonType").particle.children[1].element
        assert partner.type_name == "t:PersonType"

    def test_simple_type(self, model) -> None:
        name = _find_simple(model, "NameType")
        assert name.base == "t:NameType~original"
        assert [(f.kind, f.value) for f in name.facets] == [("maxLength", "40")]
        assert _find_simple(model, "NameType~original").base == "xs:string"

    def test_group_refers_to_the_original_among_its_particles(self, model) -> None:
        contact = next(g for g in model.groups if g.name == "Contact")
        own, phone = contact.particle.children
        assert own.group_ref == "t:Contact~original"
        assert phone.element.name == "phone"
        assert any(g.name == "Contact~original" for g in model.groups)

    def test_attribute_group(self, model) -> None:
        common = next(g for g in model.attribute_groups if g.name == "Common")
        assert common.attribute_group_refs == ["t:Common~original"]
        assert [a.name for a in common.attributes] == ["lang"]

    def test_directive_links_redefinition_and_original(self, model) -> None:
        (directive,) = model.redefines
        base = next(f for f in model.files if f.filename == "redefine-base.xsd")
        assert directive.target_file_id == base.id
        assert {(r.kind, r.redefinition_id, r.original_id) for r in directive.redefinitions} >= {
            (
                "complexType",
                "complexType:{urn:redefine}PersonType",
                "complexType:{urn:redefine}PersonType~original",
            )
        }
        assert len(directive.redefinitions) == 4
        assert model.diagnostics == []

    def test_sample_carries_base_and_redefined_content(self, model) -> None:
        xml = generate_sample(model, _find_element(model, "person"))
        root = etree.fromstring(xml.encode())
        assert [etree.QName(c).localname for c in root] == ["name", "email", "phone"]
        assert set(root.attrib) == {"lang"}
        assert validate_xml(model, xml.encode()).is_valid

    def test_missing_original_is_reported(self, redefine_xsd_bytes: bytes) -> None:
        base = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:redefine"/>'
        model = parse_files_map(
            {"redefine.xsd": redefine_xsd_bytes, "redefine-base.xsd": base},
            main_filename="redefine.xsd",
        )
        assert _find_complex(model, "PersonType").base == "t:PersonType"
        assert model.redefines[0].redefinitions[0].original_id is None
        assert sum("xs:redefine of" in d.message for d in model.diagnostics) == 4

    def test_chameleon_redefine(self) -> None:
        base = (
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            b'<xs:simpleType name="Code"><xs:restriction base="xs:string"/></xs:simpleType>'
            b"</xs:schema>"
        )
        main = (
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:c">'
            b'<xs:redefine schemaLocation="base.xsd"><xs:simpleType name="Code">'
            b'<xs:restriction base="Code"><xs:length value="3"/></xs:restriction>'
            b"</xs:simpleType></xs:redefine></xs:schema>"
        )
        model = parse_files_map({"main.xsd": main, "base.xsd": base}, main_filename="main.xsd")
        assert _find_simple(model, "Code").base == "Code~original"
        assert _find_simple(model, "Code~original") is not None


class TestAnyAttribute:
    XSD = b"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:complexType name="Open">
        <xs:attribute name="a" type="xs:string"/>
        <xs:anyAttribute namespace="##other" processContents="lax">
          <xs:annotation><xs:documentation>extension point</xs:documentation></xs:annotation>
        </xs:anyAttribute>
      </xs:complexType>
      <xs:complexType name="Derived">
        <xs:complexContent>
          <xs:extension base="Open">
            <xs:anyAttribute notNamespace="urn:x" notQName="##defined"/>
          </xs:extension>
        </xs:complexContent>
      </xs:complexType>
      <xs:complexType name="Text">
        <xs:simpleContent>
          <xs:extension base="xs:string"><xs:anyAttribute processContents="skip"/></xs:extension>
        </xs:simpleContent>
      </xs:complexType>
      <xs:complexType name="Closed"><xs:attribute name="a" type="xs:string"/></xs:complexType>
      <xs:attributeGroup name="Ext"><xs:anyAttribute namespace="urn:a urn:b"/></xs:attributeGroup>
    </xs:schema>"""

    def test_on_complex_type(self) -> None:
        model = parse_single(self.XSD, "any.xsd")
        wildcard = _find_complex(model, "Open").any_attribute
        assert (wildcard.namespace, wildcard.process_contents) == ("##other", "lax")
        assert wildcard.annotation.documentation[0].text == "extension point"
        assert _find_complex(model, "Closed").any_attribute is None

    def test_inside_derivation(self) -> None:
        model = parse_single(self.XSD, "any.xsd")
        derived = _find_complex(model, "Derived").any_attribute
        assert (derived.not_namespace, derived.not_qname) == ("urn:x", "##defined")
        assert _find_complex(model, "Text").any_attribute.process_contents == "skip"

    def test_on_attribute_group(self) -> None:
        model = parse_single(self.XSD, "any.xsd")
        assert model.attribute_groups[0].any_attribute.namespace == "urn:a urn:b"


class TestSchemaDetails:
    XSD = b"""<!-- licence -->
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:d" targetNamespace="urn:d"
        version="3.2" blockDefault="substitution" finalDefault="#all">
      <xs:annotation><xs:documentation xml:lang="en">About this schema</xs:documentation></xs:annotation>
      <xs:notation name="gif" public="image/gif" system="viewer.exe"/>
      <xs:element name="head" abstract="true"/>
      <xs:element name="other" block="#all" final=""/>
      <xs:element name="member" substitutionGroup="t:head  t:other"/>
      <xs:complexType name="Mixed" block="extension">
        <xs:complexContent mixed="true">
          <xs:extension base="t:Plain">
            <xs:sequence>
              <xs:element name="far" type="xs:string" targetNamespace="urn:far"/>
              <xs:any notNamespace="urn:d ##local" notQName="##defined t:head" processContents="lax"/>
            </xs:sequence>
            <xs:attribute name="code" type="xs:string" targetNamespace="urn:far" use="required"/>
          </xs:extension>
        </xs:complexContent>
      </xs:complexType>
      <xs:complexType name="Plain" mixed="true" final="restriction">
        <xs:complexContent mixed="false">
          <xs:restriction base="xs:anyType"/>
        </xs:complexContent>
      </xs:complexType>
      <xs:complexType name="Text">
        <xs:simpleContent><xs:extension base="xs:string"/></xs:simpleContent>
      </xs:complexType>
      <xs:complexType name="Checked">
        <xs:simpleContent>
          <xs:restriction base="t:Text">
            <xs:maxLength value="5"/>
            <xs:assertion test="$value != 'x'"/>
          </xs:restriction>
        </xs:simpleContent>
      </xs:complexType>
      <xs:simpleType name="Code" final="list union"><xs:restriction base="xs:string"/></xs:simpleType>
      <xs:simpleType name="Open"><xs:restriction base="xs:string"/></xs:simpleType>
      <xs:element name="doc" type="t:Mixed"/>
    </xs:schema>"""

    @pytest.fixture
    def model(self):
        return parse_single(self.XSD, "details.xsd")

    def test_schema_annotation_and_version(self, model) -> None:
        assert model.annotation.documentation[0].text == "About this schema"
        assert model.annotation.documentation[0].lang == "en"
        assert model.annotation.comments == [" licence "]
        assert model.schema_version == "3.2"
        assert parse_single(b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>').annotation is None

    def test_notation(self, model) -> None:
        (gif,) = model.notations
        assert (gif.id, gif.name, gif.public, gif.system) == (
            "notation:{urn:d}gif",
            "gif",
            "image/gif",
            "viewer.exe",
        )

    def test_several_substitution_group_heads(self, model) -> None:
        member = _find_element(model, "member")
        assert member.substitution_groups == ["t:head", "t:other"]
        assert member.substitution_group == "t:head"
        assert _find_element(model, "head").substitution_groups == []

    def test_block_and_final_with_schema_defaults(self, model) -> None:
        head = _find_element(model, "head")
        assert (head.block, head.final) == (["substitution"], ["extension", "restriction"])
        other = _find_element(model, "other")
        assert (other.block, other.final) == (["extension", "restriction", "substitution"], [])
        mixed = _find_complex(model, "Mixed")
        # blockDefault's "substitution" does not apply to a type.
        assert (mixed.block, mixed.final) == (["extension"], ["extension", "restriction"])
        plain = _find_complex(model, "Plain")
        assert (plain.block, plain.final) == ([], ["restriction"])
        assert _find_simple(model, "Code").final == ["list", "union"]
        assert _find_simple(model, "Open").final == ["restriction", "list", "union", "extension"]
        local = mixed.particle.children[0].element
        assert (local.block, local.final) == (["substitution"], [])

    def test_mixed_on_complex_content_wins(self, model) -> None:
        mixed = _find_complex(model, "Mixed")
        assert (mixed.mixed, mixed.content_kind) == (True, "mixed")
        plain = _find_complex(model, "Plain")
        assert (plain.mixed, plain.content_kind) == (False, "complex")

    def test_wildcard_exclusions_on_a_particle(self, model) -> None:
        wildcard = _find_complex(model, "Mixed").particle.children[1]
        assert wildcard.wildcard_not_namespace == "urn:d ##local"
        assert wildcard.wildcard_not_qname == "##defined t:head"

    def test_local_target_namespace(self, model) -> None:
        mixed = _find_complex(model, "Mixed")
        assert mixed.particle.children[0].element.target_namespace == "urn:far"
        assert mixed.attributes[0].target_namespace == "urn:far"
        root = etree.fromstring(generate_sample(model, _find_element(model, "doc")).encode())
        assert root[0].tag == "{urn:far}far"
        assert "{urn:far}code" in root.attrib

    def test_assertion_facet_of_a_simple_content_restriction(self, model) -> None:
        checked = _find_complex(model, "Checked")
        assert [a.test for a in checked.assertions] == ["$value != 'x'"]
        assert [f.kind for f in checked.simple_content_facets] == ["maxLength"]


def test_strict_wildcard_skips_excluded_namespaces() -> None:
    other = (
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:o">'
        b'<xs:element name="ok" type="xs:string"/></xs:schema>'
    )
    main = (
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:m">'
        b'<xs:import namespace="urn:o" schemaLocation="o.xsd"/>'
        b'<xs:element name="own" type="xs:string"/>'
        b'<xs:element name="root"><xs:complexType><xs:sequence>'
        b'<xs:any notNamespace="##targetNamespace"/>'
        b"</xs:sequence></xs:complexType></xs:element></xs:schema>"
    )
    model = parse_files_map({"m.xsd": main, "o.xsd": other}, main_filename="m.xsd")
    root = etree.fromstring(generate_sample(model, _find_element(model, "root")).encode())
    assert [c.tag for c in root] == ["{urn:o}ok"]


def test_member_of_a_second_substitution_head_stands_in_for_it() -> None:
    xsd = (
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        b'<xs:element name="a" abstract="true"/><xs:element name="b" abstract="true"/>'
        b'<xs:element name="m" substitutionGroup="a b" type="xs:string"/>'
        b'<xs:element name="root"><xs:complexType><xs:sequence><xs:element ref="b"/>'
        b"</xs:sequence></xs:complexType></xs:element></xs:schema>"
    )
    model = parse_single(xsd, "heads.xsd")
    root = etree.fromstring(generate_sample(model, _find_element(model, "root")).encode())
    assert [c.tag for c in root] == ["m"]


class TestConditionalInclusion:
    """vc:* is evaluated as an XSD 1.1 processor does (XSD 1.1, 4.2.2)."""

    _HEAD = (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning" xmlns:x="urn:x">'
    )

    def _names(self, body: str) -> list[str]:
        model = parse_single((self._HEAD + body + "</xs:schema>").encode(), "vc.xsd")
        return [e.name for e in model.elements]

    def test_the_1_1_branch_of_a_two_version_schema_is_the_one_kept(self) -> None:
        model = parse_single(
            (
                self._HEAD
                + '<xs:element name="A" type="xs:dateTimeStamp" vc:minVersion="1.1"/>'
                + '<xs:element name="A" type="xs:dateTime" vc:maxVersion="1.1"/>'
                + "</xs:schema>"
            ).encode(),
            "vc.xsd",
        )
        (a,) = model.elements  # used to be two declarations under one id
        assert a.type_name == "xs:dateTimeStamp"
        # The only vc:* attribute left is no reason to miss that this is XSD 1.1.
        assert model.xsd_version == "1.1"

    @pytest.mark.parametrize(
        ("condition", "kept"),
        [
            ('vc:minVersion="1.0"', True),
            ('vc:minVersion="1.1"', True),
            ('vc:minVersion="1.2"', False),
            ('vc:maxVersion="1.2"', True),
            ('vc:maxVersion="1.1"', False),
            ('vc:minVersion="1.0" vc:maxVersion="1.1"', False),
            ('vc:typeAvailable="xs:dateTimeStamp xs:int"', True),
            ('vc:typeAvailable="xs:dateTimeStamp x:custom"', False),
            ('vc:typeUnavailable="xs:dateTimeStamp"', False),
            ('vc:typeUnavailable="xs:int x:custom"', True),
            ('vc:facetAvailable="xs:assertion"', True),
            ('vc:facetAvailable="x:minLen"', False),
            ('vc:facetUnavailable="xs:explicitTimezone"', False),
            ('vc:facetUnavailable="x:minLen"', True),
            ('vc:minVersion="soon"', True),
        ],
    )
    def test_conditions(self, condition: str, kept: bool) -> None:
        assert self._names(f'<xs:element name="A" type="xs:int" {condition}/>') == (
            ["A"] if kept else []
        )

    def test_it_applies_at_any_depth_and_takes_the_content_along(self) -> None:
        model = parse_single(
            (
                self._HEAD
                + '<xs:element name="Doc"><xs:complexType><xs:sequence>'
                + '<xs:element name="Old" vc:maxVersion="1.1"><xs:complexType>'
                + '<xs:attribute name="deep" vc:minVersion="1.1"/></xs:complexType></xs:element>'
                + '<xs:element name="New" type="xs:int"/>'
                + '</xs:sequence><xs:attribute name="legacy" vc:maxVersion="1.1"/>'
                + "</xs:complexType></xs:element></xs:schema>"
            ).encode(),
            "vc.xsd",
        )
        doc = model.elements[0].type_inline_complex
        assert [c.element.name for c in doc.particle.children] == ["New"]
        assert doc.attributes == []
        (warning,) = model.diagnostics
        assert "2 declarations were left out" in warning.message

    def test_an_excluded_include_is_not_followed(self) -> None:
        model = parse_files_map(
            {
                "main.xsd": (
                    self._HEAD
                    + '<xs:include schemaLocation="old.xsd" vc:maxVersion="1.1"/>'
                    + '<xs:include schemaLocation="missing.xsd" vc:maxVersion="1.1"/>'
                    + '<xs:element name="A"/></xs:schema>'
                ).encode(),
                "old.xsd": (
                    b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
                    b'<xs:element name="Old"/></xs:schema>'
                ),
            },
            main_filename="main.xsd",
        )
        assert [f.filename for f in model.files] == ["main.xsd"]
        assert [e.name for e in model.elements] == ["A"]
        assert not any("unresolved" in d.message for d in model.diagnostics)


class TestSchemaDefaultsPerFile:
    """defaultAttributes and xs:defaultOpenContent reach the types of their own file only."""

    def _model(self):
        xs = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        return parse_files_map(
            {
                "main.xsd": (
                    f'<xs:schema {xs}><xs:include schemaLocation="part.xsd"/>'
                    '<xs:complexType name="Main"><xs:sequence><xs:element name="a"/></xs:sequence>'
                    "</xs:complexType>"
                    '<xs:complexType name="Ext"><xs:complexContent><xs:extension base="Open">'
                    '<xs:sequence><xs:element name="more"/></xs:sequence>'
                    "</xs:extension></xs:complexContent></xs:complexType>"
                    '<xs:complexType name="Restr"><xs:complexContent><xs:restriction base="Open">'
                    '<xs:sequence><xs:element name="b"/></xs:sequence>'
                    "</xs:restriction></xs:complexContent></xs:complexType>"
                    "</xs:schema>"
                ).encode(),
                "part.xsd": (
                    f'<xs:schema {xs} defaultAttributes="Common">'
                    '<xs:defaultOpenContent mode="suffix"><xs:any processContents="lax"/>'
                    "</xs:defaultOpenContent>"
                    '<xs:attributeGroup name="Common"><xs:attribute name="lang"/></xs:attributeGroup>'
                    '<xs:complexType name="Open"><xs:sequence><xs:element name="b"/></xs:sequence>'
                    "</xs:complexType>"
                    '<xs:complexType name="Empty"/>'
                    '<xs:complexType name="Plain" defaultAttributesApply="false">'
                    '<xs:openContent mode="none"/><xs:sequence><xs:element name="c"/></xs:sequence>'
                    "</xs:complexType>"
                    '<xs:complexType name="Text"><xs:simpleContent><xs:extension base="xs:string"/>'
                    "</xs:simpleContent></xs:complexType>"
                    "</xs:schema>"
                ).encode(),
            },
            main_filename="main.xsd",
        )

    def test_default_attributes_are_those_of_the_types_own_file(self) -> None:
        model = self._model()
        assert model.default_attributes is None  # the main file names none
        assert _find_complex(model, "Open").default_attributes == "Common"
        assert _find_complex(model, "Text").default_attributes == "Common"
        assert _find_complex(model, "Plain").default_attributes is None
        assert _find_complex(model, "Main").default_attributes is None

    def test_default_open_content_is_that_of_the_types_own_file(self) -> None:
        model = self._model()
        assert model.default_open_content is None
        opened = _find_complex(model, "Open").open_content
        assert (opened.origin, opened.mode) == ("default", "suffix")
        assert _find_complex(model, "Main").open_content is None
        # Not an empty content model unless appliesToEmpty says so, and never simple content.
        assert _find_complex(model, "Empty").open_content is None
        assert _find_complex(model, "Text").open_content is None
        assert _find_complex(model, "Plain").open_content.mode == "none"

    def test_an_extension_keeps_its_bases_open_content_a_restriction_does_not(self) -> None:
        model = self._model()
        inherited = _find_complex(model, "Ext").open_content
        assert (inherited.origin, inherited.mode) == ("base", "suffix")
        assert _find_complex(model, "Restr").open_content is None

    def test_a_sample_carries_the_default_attributes_of_an_included_file(self) -> None:
        from app.parser.sample import generate_sample

        xs = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        model = parse_files_map(
            {
                "main.xsd": (
                    f'<xs:schema {xs}><xs:include schemaLocation="part.xsd"/>'
                    '<xs:element name="Doc" type="T"/></xs:schema>'
                ).encode(),
                "part.xsd": (
                    f'<xs:schema {xs} defaultAttributes="Common">'
                    '<xs:attributeGroup name="Common">'
                    '<xs:attribute name="lang" use="required"/></xs:attributeGroup>'
                    '<xs:complexType name="T"/></xs:schema>'
                ).encode(),
            },
            main_filename="main.xsd",
        )
        assert "lang=" in generate_sample(model, _find_element(model, "Doc"))


class TestXsd11Detection:
    """A schema is 1.1 as soon as it uses anything 1.0 does not have."""

    @pytest.mark.parametrize(
        "body",
        [
            '<xs:element name="a" type="xs:dateTimeStamp"/>',
            '<xs:simpleType name="t"><xs:restriction base="xs:dayTimeDuration"/></xs:simpleType>',
            '<xs:simpleType name="t"><xs:union memberTypes="xs:int xs:yearMonthDuration"/>'
            "</xs:simpleType>",
            '<xs:attribute name="a" inheritable="true"/>',
            '<xs:complexType name="t"><xs:sequence><xs:any notQName="##defined"/></xs:sequence>'
            "</xs:complexType>",
            '<xs:complexType name="t"><xs:anyAttribute notNamespace="urn:x"/></xs:complexType>',
            '<xs:complexType name="t" defaultAttributesApply="false"/>',
            '<xs:element name="a" substitutionGroup="b c"/>',
            '<xs:complexType name="t"><xs:all><xs:element name="a" maxOccurs="3"/></xs:all>'
            "</xs:complexType>",
            '<xs:complexType name="t"><xs:all><xs:any/></xs:all></xs:complexType>',
            '<xs:complexType name="t"><xs:sequence>'
            '<xs:element name="a" targetNamespace="urn:other"/></xs:sequence></xs:complexType>',
        ],
    )
    def test_features_without_an_element_of_their_own(self, body: str) -> None:
        xsd = f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">{body}</xs:schema>'
        assert parse_single(xsd.encode(), "v.xsd").xsd_version == "1.1"

    def test_a_schema_attribute(self) -> None:
        xsd = (
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            'xpathDefaultNamespace="##targetNamespace"/>'
        )
        assert parse_single(xsd.encode(), "v.xsd").xsd_version == "1.1"

    def test_a_type_of_that_name_in_another_namespace_is_not_a_reason(self) -> None:
        xsd = (
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t" '
            'targetNamespace="urn:t"><xs:simpleType name="error"><xs:restriction base="xs:string"/>'
            '</xs:simpleType><xs:element name="a" type="t:error"/>'
            '<xs:complexType name="c"><xs:all><xs:element name="b" minOccurs="0"/></xs:all>'
            "</xs:complexType></xs:schema>"
        )
        assert parse_single(xsd.encode(), "v.xsd").xsd_version == "1.0"


class TestInnerAnnotations:
    _XSD = b"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:jaxb="https://jakarta.ee/xml/ns/jaxb" xpathDefaultNamespace="urn:schema">
  <xs:import namespace="urn:other">
    <xs:annotation><xs:documentation>Why we import it</xs:documentation></xs:annotation>
  </xs:import>
  <xs:simpleType name="Code" id="code-type" jaxb:class="CodeValue">
    <xs:annotation>
      <xs:documentation source="https://example.com/codes" xml:lang="en">A code</xs:documentation>
    </xs:annotation>
    <xs:restriction base="xs:string">
      <xs:annotation><xs:documentation>Why restricted</xs:documentation>
        <xs:appinfo source="urn:tool">hint</xs:appinfo></xs:annotation>
      <xs:maxLength value="3"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:complexType name="Ext">
    <xs:complexContent>
      <xs:annotation><xs:documentation>About the content</xs:documentation></xs:annotation>
      <xs:extension base="Base">
        <xs:annotation><xs:documentation>About the extension</xs:documentation></xs:annotation>
        <xs:sequence>
          <xs:element name="inner"><xs:simpleType><xs:restriction base="xs:string">
            <xs:annotation><xs:documentation>Belongs to inner</xs:documentation></xs:annotation>
          </xs:restriction></xs:simpleType></xs:element>
        </xs:sequence>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:complexType name="Base"/>
  <xs:element name="Doc" type="Ext">
    <xs:key name="k">
      <xs:selector xpath="inner"><xs:annotation>
        <xs:documentation>Which rows</xs:documentation></xs:annotation></xs:selector>
      <xs:field xpath="@a"/>
      <xs:field xpath="@b" xpathDefaultNamespace="urn:field"/>
    </xs:key>
  </xs:element>
</xs:schema>"""

    def test_annotations_of_inner_elements_are_kept_with_their_context(self) -> None:
        model = parse_single(self._XSD, "inner.xsd")
        code = _find_simple(model, "Code").annotation
        assert [(d.text, d.context) for d in code.documentation] == [
            ("A code", None),
            ("Why restricted", "restriction"),
        ]
        assert [(a.source_uri, a.context) for a in code.appinfo] == [("urn:tool", "restriction")]
        ext = _find_complex(model, "Ext").annotation
        # Not what belongs to the element declared further inside.
        assert [(d.text, d.context) for d in ext.documentation] == [
            ("About the content", "complexContent"),
            ("About the extension", "extension"),
        ]
        key = _find_element(model, "Doc").identity_constraints[0]
        assert [(d.text, d.context) for d in key.annotation.documentation] == [
            ("Which rows", "selector")
        ]
        assert [(d.text, d.context) for d in model.annotation.documentation] == [
            ("Why we import it", "import urn:other")
        ]

    def test_documentation_source_id_and_foreign_attributes(self) -> None:
        model = parse_single(self._XSD, "inner.xsd")
        code = _find_simple(model, "Code").annotation
        assert code.documentation[0].source_uri == "https://example.com/codes"
        assert code.xml_id == "code-type"
        (attribute,) = code.attributes
        assert (attribute.qname, attribute.namespace, attribute.name, attribute.value) == (
            "jaxb:class",
            "https://jakarta.ee/xml/ns/jaxb",
            "class",
            "CodeValue",
        )
        # A component with nothing written about it still has no annotation.
        assert _find_complex(model, "Base").annotation is None

    def test_xpath_default_namespace_falls_back_to_the_files(self) -> None:
        model = parse_single(self._XSD, "inner.xsd")
        key = _find_element(model, "Doc").identity_constraints[0]
        assert key.xpath_default_namespace == "urn:schema"
        assert key.field_xpath_default_namespaces == ["urn:schema", "urn:field"]
