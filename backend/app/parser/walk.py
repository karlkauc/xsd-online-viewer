"""Shared read-only walkers over a parsed :class:`SchemaModel`.

These generators traverse the model graph (elements nested in content
models, inline types, XSD 1.1 type alternatives) without following named
references (``ref``/``type``/``group ref``/``base``) across declarations —
each named declaration is only visited once, from wherever it is actually
defined in the model's flat lists. Consumers that need cross-reference
resolution (e.g. following a ``ref`` to its target) do that themselves.

Originally lived in ``validation.py`` (used there to resolve XML validation
errors back to a schema declaration); moved here so other post-passes
(identity-constraint linking, ID/IDREF classification) can reuse the same
traversal without importing from the validation module.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.parser.model import (
    AttributeDecl,
    ComplexType,
    ElementDecl,
    Group,
    Particle,
    SchemaModel,
)


def _iter_particle(particle: Particle | None) -> Iterator[object]:
    if particle is None:
        return
    if particle.element is not None:
        yield from _iter_element(particle.element)
    if particle.group_inline is not None:
        yield from _iter_group(particle.group_inline)
    for child in particle.children:
        yield from _iter_particle(child)


def _iter_element(element: ElementDecl) -> Iterator[object]:
    yield element
    if element.type_inline_complex is not None:
        yield from _iter_complex(element.type_inline_complex)
    if element.type_inline_simple is not None:
        yield element.type_inline_simple
    for alternative in element.alternatives:
        if alternative.type_inline_complex is not None:
            yield from _iter_complex(alternative.type_inline_complex)
        if alternative.type_inline_simple is not None:
            yield alternative.type_inline_simple


def _iter_complex(ct: ComplexType) -> Iterator[object]:
    yield ct
    yield from _iter_particle(ct.particle)
    yield from ct.attributes


def _iter_group(group: Group) -> Iterator[object]:
    yield group
    yield from _iter_particle(group.particle)


def _iter_declarations(model: SchemaModel) -> Iterator[object]:
    """Yield every named-or-local declaration, including ones nested inside
    complex types / groups / XSD 1.1 alternatives, so local elements (e.g.
    ``<Age>`` inside a content model) can still be resolved."""
    for element in model.elements:
        yield from _iter_element(element)
    for ct in model.complex_types:
        yield from _iter_complex(ct)
    yield from model.simple_types
    yield from model.attributes
    for group in model.groups:
        yield from _iter_group(group)
    for ag in model.attribute_groups:
        yield ag
        yield from ag.attributes


def iter_elements(model: SchemaModel) -> Iterator[ElementDecl]:
    """Yield every :class:`ElementDecl` reachable from ``model``: top-level
    elements plus every element nested in a content model (complex types,
    groups) or an XSD 1.1 type alternative."""
    for decl in _iter_declarations(model):
        if isinstance(decl, ElementDecl):
            yield decl


def iter_attributes(model: SchemaModel) -> Iterator[AttributeDecl]:
    """Yield every :class:`AttributeDecl` reachable from ``model``: top-level
    attributes plus every attribute declared inline on a complex type or
    attribute group."""
    for decl in _iter_declarations(model):
        if isinstance(decl, AttributeDecl):
            yield decl
