"""Compare two parsed schemas: what a new release adds, removes and changes.

The comparison works per *container* — a named complex type, a global element,
or an anonymous type nested below one of them (``Fund/FundStaticData``) — and
lists the child elements with their type and cardinality. Named references are
not expanded, so every change shows up once, where it was made, and the size of
the result stays proportional to the schema rather than to its instance tree.
Enumerations are compared per simple type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.model import ComplexType, ElementDecl, Particle, SchemaModel, SimpleType


@dataclass
class ContainerChange:
    container: str
    added: list[str] = field(default_factory=list)  # "Name (Type, 0..1)"
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)  # "Name: Type 1..1 → Type 0..1"


@dataclass
class EnumChange:
    type_name: str
    added: list[str]
    removed: list[str]


@dataclass
class SchemaDiff:
    added_elements: list[str] = field(default_factory=list)
    removed_elements: list[str] = field(default_factory=list)
    added_types: list[str] = field(default_factory=list)
    removed_types: list[str] = field(default_factory=list)
    containers: list[ContainerChange] = field(default_factory=list)
    enums: list[EnumChange] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (
            self.added_elements
            or self.removed_elements
            or self.added_types
            or self.removed_types
            or self.containers
            or self.enums
        )


def _local(qname: str | None) -> str:
    return (qname or "").rsplit(":", 1)[-1].rsplit("}", 1)[-1]


def _occurs(particle: Particle) -> str:
    return f"{particle.min_occurs}..{'*' if particle.max_occurs == 'unbounded' else particle.max_occurs}"


def _type_label(element: ElementDecl) -> str:
    if element.ref:
        return f"ref {_local(element.ref)}"
    if element.type_name:
        return _local(element.type_name)
    if element.type_inline_complex is not None or element.type_inline_simple is not None:
        return "inline type"
    return "anyType"


def _element_particles(particle: Particle | None) -> list[Particle]:
    """Element particles of a content model, through nested compositors and inline groups."""
    if particle is None:
        return []
    found: list[Particle] = []
    if particle.element is not None:
        found.append(particle)
    if particle.group_inline is not None:
        found.extend(_element_particles(particle.group_inline.particle))
    for child in particle.children:
        found.extend(_element_particles(child))
    return found


def _group_refs(particle: Particle | None) -> list[str]:
    if particle is None:
        return []
    refs = [_local(particle.group_ref)] if particle.group_ref else []
    for child in particle.children:
        refs.extend(_group_refs(child))
    return refs


Outline = dict[str, dict[str, str]]  # container -> child name -> "Type, min..max"


def _add_complex(outline: Outline, key: str, ct: ComplexType) -> None:
    children: dict[str, str] = {}
    if ct.base and ct.derivation != "none":
        children["(base)"] = f"{ct.derivation} of {_local(ct.base)}"
    for ref in _group_refs(ct.particle):
        children[f"(group {ref})"] = "group"
    for particle in _element_particles(ct.particle):
        element = particle.element
        assert element is not None
        name = element.name or _local(element.ref)
        children[name] = f"{_type_label(element)}, {_occurs(particle)}"
        if element.type_inline_complex is not None:
            _add_complex(outline, f"{key}/{name}", element.type_inline_complex)
    for group in ct.attribute_group_refs:
        children[f"@group {_local(group)}"] = "attribute group"
    for attribute in ct.attributes:
        attr_name = attribute.name or _local(attribute.ref)
        children[f"@{attr_name}"] = f"{_local(attribute.type_name) or 'inline type'}, {attribute.use}"
    outline[key] = children


def outline(model: SchemaModel) -> Outline:
    result: Outline = {}
    for ct in model.complex_types:
        if ct.name:
            _add_complex(result, ct.name, ct)
    for group in model.groups:
        if group.name:
            # A model group is a complex type without attributes for this purpose.
            _add_complex(result, f"group {group.name}", ComplexType(id=group.id, particle=group.particle))
    for element in model.elements:
        if element.name and element.type_inline_complex is not None:
            _add_complex(result, element.name, element.type_inline_complex)
    return result


def _enum_values(st: SimpleType) -> set[str]:
    return {f.value for f in st.facets if f.kind == "enumeration"}


def enumerations(model: SchemaModel) -> dict[str, set[str]]:
    return {st.name: values for st in model.simple_types if st.name and (values := _enum_values(st))}


def diff(old: SchemaModel, new: SchemaModel) -> SchemaDiff:
    result = SchemaDiff()
    old_elements = {e.name for e in old.elements if e.name}
    new_elements = {e.name for e in new.elements if e.name}
    result.added_elements = sorted(new_elements - old_elements)
    result.removed_elements = sorted(old_elements - new_elements)
    old_types = {t.name for t in [*old.complex_types, *old.simple_types] if t.name}
    new_types = {t.name for t in [*new.complex_types, *new.simple_types] if t.name}
    result.added_types = sorted(new_types - old_types)
    result.removed_types = sorted(old_types - new_types)

    before, after = outline(old), outline(new)
    for key in sorted(before.keys() & after.keys()):
        a, b = before[key], after[key]
        change = ContainerChange(
            container=key,
            added=[f"{n} ({b[n]})" for n in b if n not in a],
            removed=[f"{n} ({a[n]})" for n in a if n not in b],
            changed=[f"{n}: {a[n]} → {b[n]}" for n in a if n in b and a[n] != b[n]],
        )
        if change.added or change.removed or change.changed:
            result.containers.append(change)

    old_enums, new_enums = enumerations(old), enumerations(new)
    for name in sorted(old_enums.keys() & new_enums.keys()):
        added = sorted(new_enums[name] - old_enums[name])
        removed = sorted(old_enums[name] - new_enums[name])
        if added or removed:
            result.enums.append(EnumChange(type_name=name, added=added, removed=removed))
    return result
