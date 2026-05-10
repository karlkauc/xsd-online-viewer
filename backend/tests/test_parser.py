"""Tests for the XSD parser — correctness on small fixture schemas."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.parser.xsd_parser import parse_files_map, parse_single, parse_zip

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

        legacy = _find_simple(model, "LegacyToken")
        assert legacy is not None
        assert legacy.version_constraints is not None
        assert legacy.version_constraints.max_version == "1.1"

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
        # An inheriting complexType has no per-type override; the default
        # propagation is purely a display concern handled in the frontend.
        assert a is not None
        assert a.open_content is None

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

    def test_original_and_replacement_coexist_in_complex_types(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        color_types = [c for c in model.complex_types if c.name == "ColorType"]
        assert len(color_types) == 2
        # Distinct ids — replacement carries the override:* prefix.
        ids = {c.id for c in color_types}
        assert any(i.startswith("override:") for i in ids)
        assert any(not i.startswith("override:") for i in ids)
        # Different content models confirm we picked up two definitions.
        kids = {
            tuple(
                child.element.name
                for child in c.particle.children
                if child.element is not None
            )
            for c in color_types
        }
        assert ("R", "G", "B") in kids
        assert ("C", "M", "Y", "K") in kids

    def test_override_directive_records_replacements(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        assert len(model.overrides) == 1
        directive = model.overrides[0]
        assert directive.target_file_id  # set to the loaded base file id
        kinds = sorted(r.kind for r in directive.replacements)
        assert kinds == ["complexType", "element"]
        names = {r.qname.split("}")[-1] for r in directive.replacements}
        assert names == {"ColorType", "AddedByOverride"}
        for r in directive.replacements:
            assert r.replacement_id.startswith("override:")
            assert r.source_ref is not None

    def test_added_by_override_is_findable_as_top_level_element(
        self,
        override_xsd_bytes: bytes,
        override_base_xsd_bytes: bytes,
    ) -> None:
        model = self._parse_pair(override_xsd_bytes, override_base_xsd_bytes)
        added = [e for e in model.elements if e.name == "AddedByOverride"]
        assert len(added) == 1
        assert added[0].id.startswith("override:")

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
