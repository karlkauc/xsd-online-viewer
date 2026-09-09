"""Generate a skeleton XML instance for an element of a parsed schema.

The generator walks the content model the way XMLSpy's "Generate Sample XML"
does: required particles once, the first branch of a choice, the first
enumeration value, type-appropriate placeholders for built-in types, and a
best-effort string for ``xs:pattern`` facets. Optional content is included
on request. It is deliberately structural — no XPath, no assertions — and
never raises on an incomplete schema: unresolved references become XML
comments so the user can see what could not be filled in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from lxml import etree

from app.parser.model import (
    AttributeDecl,
    AttributeGroup,
    ComplexType,
    ElementDecl,
    Facet,
    Group,
    Particle,
    SchemaModel,
    SimpleType,
)
from app.parser.regex_sample import sample_from_pattern
from app.parser.validation import _iter_declarations

XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

T = TypeVar("T")

# Placeholder values for the built-in types. Integers use "1" so that
# positiveInteger and friends validate; the negative family gets "-1".
_BUILTIN_VALUES: dict[str, str] = {
    "string": "string",
    "normalizedString": "string",
    "token": "token",
    "language": "en",
    "Name": "name",
    "NCName": "name",
    "NMTOKEN": "token",
    "NMTOKENS": "token",
    "ID": "id1",
    "IDREF": "id1",
    "IDREFS": "id1",
    "ENTITY": "entity",
    "ENTITIES": "entity",
    "QName": "name",
    "NOTATION": "name",
    "anyURI": "http://example.com/",
    "boolean": "true",
    "decimal": "0.0",
    "float": "0.0",
    "double": "0.0",
    "integer": "1",
    "long": "1",
    "int": "1",
    "short": "1",
    "byte": "1",
    "nonNegativeInteger": "1",
    "positiveInteger": "1",
    "unsignedLong": "1",
    "unsignedInt": "1",
    "unsignedShort": "1",
    "unsignedByte": "1",
    "nonPositiveInteger": "0",
    "negativeInteger": "-1",
    "date": "2026-01-01",
    "dateTime": "2026-01-01T00:00:00",
    "dateTimeStamp": "2026-01-01T00:00:00Z",
    "time": "00:00:00",
    "duration": "P1D",
    "dayTimeDuration": "P1D",
    "yearMonthDuration": "P1Y",
    "gYear": "2026",
    "gYearMonth": "2026-01",
    "gMonth": "--01",
    "gMonthDay": "--01-01",
    "gDay": "---01",
    "base64Binary": "AA==",
    "hexBinary": "00",
    "anySimpleType": "text",
    "anyAtomicType": "text",
    "anyType": "",
}
_INTEGER_TYPES = {
    "integer",
    "long",
    "int",
    "short",
    "byte",
    "nonNegativeInteger",
    "positiveInteger",
    "unsignedLong",
    "unsignedInt",
    "unsignedShort",
    "unsignedByte",
    "nonPositiveInteger",
    "negativeInteger",
}
_DECIMAL_TYPES = {"decimal", "float", "double"}
_STRING_TYPES = {"string", "normalizedString", "token", "Name", "NCName", "NMTOKEN", "anyURI"}


# Why the generator could not produce faithful content. ``schema_incomplete``
# means the schema did not offer what we needed (a missing import, a dangling
# ref) and there is nothing for us to fix; ``generator_limit`` means this
# generator gave up where a better one need not, and is a bug candidate.
GENERATOR_LIMIT = "generator_limit"
SCHEMA_INCOMPLETE = "schema_incomplete"


@dataclass(slots=True)
class Degradation:
    """One spot where the output deviates from what the schema asks for."""

    reason: str
    category: str
    where: str | None = None
    file_id: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "reason": self.reason,
            "category": self.category,
            "where": self.where,
            "file_id": self.file_id,
            "line": self.line,
        }


@dataclass(slots=True)
class SampleReport:
    """Everything the generator had to fudge, in document order.

    An invalid sample with an empty report is the interesting case: it means
    the generator believed it emitted faithful content and was wrong.
    """

    entries: list[Degradation] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.reason] = counts.get(entry.reason, 0) + 1
        return counts

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def as_dict(self, max_entries: int = 200) -> dict[str, object]:
        """Compact, JSON-safe form. ``counts`` stays complete when entries are cut."""
        return {
            "total": len(self.entries),
            "counts": self.counts,
            "entries": [e.as_dict() for e in self.entries[:max_entries]],
            "truncated": len(self.entries) > max_entries,
        }


@dataclass
class SampleOptions:
    include_optional: bool = False
    # Real-world schemas (FundsXML, ISO 20022) nest 20+ levels deep; the
    # recursion guard, not this limit, is what keeps output finite.
    max_depth: int = 40
    # Occurrences to emit for repeatable particles when optional content is on.
    repeat: int = 1


Key = tuple[str | None, str]


@dataclass
class _Context:
    model: SchemaModel
    options: SampleOptions
    file_namespaces: dict[str, str | None] = field(default_factory=dict)
    complex_by_key: dict[Key, ComplexType] = field(default_factory=dict)
    simple_by_key: dict[Key, SimpleType] = field(default_factory=dict)
    group_by_key: dict[Key, Group] = field(default_factory=dict)
    attr_group_by_key: dict[Key, AttributeGroup] = field(default_factory=dict)
    global_element_by_key: dict[Key, ElementDecl] = field(default_factory=dict)
    global_attribute_by_key: dict[Key, AttributeDecl] = field(default_factory=dict)
    id_counter: int = 0
    nsmap: dict[str, str] = field(default_factory=dict)
    # Number of elements left empty by the recursion/depth guards so far. An
    # optional subtree that raised it is dropped again (see _emit_element_particle).
    cuts: int = 0
    # Every spot where the output deviates from the schema, in document order.
    report: list[Degradation] = field(default_factory=list)

    def note(
        self,
        reason: str,
        category: str,
        where: str | None = None,
        decl: object | None = None,
    ) -> None:
        """Record a degradation. ``decl`` only supplies the source location."""
        ref = getattr(decl, "source_ref", None) if decl is not None else None
        self.report.append(
            Degradation(
                reason=reason,
                category=category,
                where=where,
                file_id=ref.file_id if ref else None,
                line=ref.line if ref else None,
            )
        )

    # -- lookups ---------------------------------------------------------

    def namespace_of_prefix(self, prefix: str | None) -> str | None:
        if prefix is None:
            # An unprefixed QName means the default namespace, which for
            # a schema is almost always its own target namespace.
            return self.model.target_namespace
        return self.model.namespaces.get(prefix)

    def split_qname(self, qname: str) -> Key:
        if qname.startswith("{"):
            ns, _, local = qname[1:].partition("}")
            return ns, local
        prefix, sep, local = qname.rpartition(":")
        if not sep:
            return self.namespace_of_prefix(None), qname
        return self.namespace_of_prefix(prefix), local

    def lookup_exact(self, table: dict[Key, T], qname: str) -> T | None:
        """Only a real ``(namespace, name)`` hit — no local-name guessing."""
        return table.get(self.split_qname(qname))

    def lookup_loose(self, table: dict[Key, T], qname: str) -> T | None:
        """The local name alone, in any namespace (prefix undeclared / chameleon include)."""
        _, local = self.split_qname(qname)
        for (_, name), value in table.items():
            if name == local:
                return value
        return None

    def lookup(self, table: dict[Key, T], qname: str) -> T | None:
        hit = self.lookup_exact(table, qname)
        return hit if hit is not None else self.lookup_loose(table, qname)

    def declared_namespace(self, decl_file_id: str | None) -> str | None:
        if decl_file_id is not None and decl_file_id in self.file_namespaces:
            return self.file_namespaces[decl_file_id]
        return self.model.target_namespace

    def namespace_of(self, decl: object) -> str | None:
        ref = getattr(decl, "source_ref", None)
        return self.declared_namespace(ref.file_id if ref else None)

    def next_id(self) -> str:
        self.id_counter += 1
        return f"id{self.id_counter}"

    def prefix_for(self, namespace: str) -> str:
        for prefix, uri in self.nsmap.items():
            if uri == namespace:
                return prefix
        for prefix, uri in self.model.namespaces.items():
            if uri == namespace and prefix and prefix not in self.nsmap:
                self.nsmap[prefix] = namespace
                return prefix
        prefix = f"ns{len(self.nsmap) + 1}"
        self.nsmap[prefix] = namespace
        return prefix


def _resolve_type(
    ctx: _Context, type_name: str, decl: object | None = None
) -> tuple[str, str] | tuple[str, SimpleType] | tuple[str, ComplexType] | None:
    """Classify a type reference: ("builtin", local) | ("simple", st) | ("complex", ct).

    An unprefixed name (``type="ID"`` in a schema whose default namespace is
    the XSD namespace) is tried against the schema's own types first and
    falls back to the built-in type of that name, because the merged
    prefix map cannot tell per-file default namespaces apart.

    Both tables are searched exactly *before* either is searched by local name:
    the local-name fallback is a guess for undeclared prefixes and chameleon
    includes, and letting it run inside the simpleType lookup first let a
    same-named simpleType in any other namespace beat the correctly referenced
    complexType — which put a text placeholder into an element-only element.
    """
    ns, local = ctx.split_qname(type_name)
    if ns == XSD_NS:
        return ("builtin", local)
    simple = ctx.lookup_exact(ctx.simple_by_key, type_name)
    if simple is not None:
        return ("simple", simple)
    complex_type = ctx.lookup_exact(ctx.complex_by_key, type_name)
    if complex_type is not None:
        return ("complex", complex_type)
    if ":" not in type_name and not type_name.startswith("{") and local in _BUILTIN_VALUES:
        return ("builtin", local)
    # Nothing matched exactly; guess by local name, and say that we guessed.
    simple = ctx.lookup_loose(ctx.simple_by_key, type_name)
    complex_type = None if simple is not None else ctx.lookup_loose(ctx.complex_by_key, type_name)
    if simple is None and complex_type is None:
        return None
    ctx.note("type_resolved_by_local_name", GENERATOR_LIMIT, type_name, decl)
    return ("simple", simple) if simple is not None else ("complex", complex_type)


def _build_context(model: SchemaModel, options: SampleOptions) -> _Context:
    ctx = _Context(model=model, options=options)
    ctx.file_namespaces = {f.id: f.target_namespace for f in model.files}
    for ct in model.complex_types:
        if ct.name:
            ctx.complex_by_key.setdefault((ctx.namespace_of(ct), ct.name), ct)
    for st in model.simple_types:
        if st.name:
            ctx.simple_by_key.setdefault((ctx.namespace_of(st), st.name), st)
    for group in model.groups:
        if group.name:
            ctx.group_by_key.setdefault((ctx.namespace_of(group), group.name), group)
    for ag in model.attribute_groups:
        if ag.name:
            ctx.attr_group_by_key.setdefault((ctx.namespace_of(ag), ag.name), ag)
    for element in model.elements:
        if element.name:
            key = (element.target_namespace or ctx.namespace_of(element), element.name)
            ctx.global_element_by_key.setdefault(key, element)
    for attribute in model.attributes:
        if attribute.name:
            key = (attribute.target_namespace or ctx.namespace_of(attribute), attribute.name)
            ctx.global_attribute_by_key.setdefault(key, attribute)
    return ctx


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def find_element(model: SchemaModel, element_id: str) -> ElementDecl | None:
    for decl in _iter_declarations(model):
        if isinstance(decl, ElementDecl) and decl.id == element_id:
            return decl
    return None


def generate_sample(
    model: SchemaModel, element: ElementDecl, options: SampleOptions | None = None
) -> str:
    """Return a pretty-printed XML document rooted at ``element``."""
    return generate_sample_with_report(model, element, options)[0]


def generate_sample_with_report(
    model: SchemaModel, element: ElementDecl, options: SampleOptions | None = None
) -> tuple[str, SampleReport]:
    """Like :func:`generate_sample`, plus everything the generator had to fudge.

    The report is what tells a generator bug apart from an incomplete schema,
    so the usage statistics keep it — see ``app.usage.sample_issue``.
    """
    options = options or SampleOptions()
    ctx = _build_context(model, options)
    element = _deref_element(ctx, element) or element
    if element.abstract:
        # An abstract root can never validate ("the element declaration is
        # abstract"), so substitute it the way a child particle would.
        substitute = _substitution_member(ctx, element)
        if substitute is None:
            ctx.note("abstract_no_substitution", SCHEMA_INCOMPLETE, element.name, element)
        else:
            element = substitute
    namespace = _element_namespace(ctx, element, is_root=True)
    if namespace:
        ctx.prefix_for(namespace)
    root = etree.Element(_tag(namespace, element.name))
    _fill_element(ctx, root, element, depth=0, type_stack=())
    # Declare the prefixes we used (and only those) on the root.
    nsmap = dict(ctx.nsmap)
    if any(f"{{{XSI_NS}}}nil" in el.attrib for el in root.iter(etree.Element)):
        nsmap["xsi"] = XSI_NS
    if nsmap:
        new_root = etree.Element(root.tag, nsmap=nsmap)
        for key, value in root.attrib.items():
            new_root.set(key, value)
        new_root.text = root.text
        for child in list(root):
            new_root.append(child)
        root = new_root
    etree.cleanup_namespaces(root)
    document = etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    ).decode("utf-8")
    return document, SampleReport(entries=ctx.report)


def _tag(namespace: str | None, name: str | None) -> str:
    local = name or "element"
    return f"{{{namespace}}}{local}" if namespace else local


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------


def _deref_element(ctx: _Context, element: ElementDecl) -> ElementDecl | None:
    if not element.ref:
        return element
    return ctx.lookup(ctx.global_element_by_key, element.ref)


def _element_namespace(ctx: _Context, element: ElementDecl, *, is_root: bool) -> str | None:
    if element.target_namespace:
        return element.target_namespace
    if element.is_global or is_root:
        return ctx.namespace_of(element)
    form = element.form or ctx.model.element_form_default
    return ctx.namespace_of(element) if form == "qualified" else None


def _fill_element(
    ctx: _Context,
    node: etree._Element,
    element: ElementDecl,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    if element.fixed is not None:
        node.text = element.fixed
        return
    if element.type_inline_simple is not None:
        node.text = (
            element.default
            if element.default is not None
            else _simple_value(ctx, element.type_inline_simple, ())
        )
        return
    if element.type_inline_complex is not None:
        _fill_complex(ctx, node, element.type_inline_complex, depth=depth, type_stack=type_stack)
        return
    if element.type_name is None:
        # xs:anyType — leave empty.
        if element.default is not None:
            node.text = element.default
        return
    resolved = _resolve_type(ctx, element.type_name, element)
    if resolved is None:
        node.append(etree.Comment(f" type {element.type_name} not found in schema "))
        ctx.note("type_not_found", SCHEMA_INCOMPLETE, element.type_name, element)
        return
    kind, target = resolved
    if kind == "builtin":
        node.text = element.default if element.default is not None else _builtin_value(ctx, target, [])
    elif kind == "simple":
        node.text = element.default if element.default is not None else _simple_value(ctx, target, ())
    else:
        if target.id in type_stack:
            node.append(etree.Comment(f" recursive {element.type_name} omitted "))
            ctx.note("recursion_cut", GENERATOR_LIMIT, element.type_name, element)
            ctx.cuts += 1
            return
        _fill_complex(ctx, node, target, depth=depth, type_stack=type_stack + (target.id,))


# ---------------------------------------------------------------------------
# Complex types
# ---------------------------------------------------------------------------


def _base_chain(ctx: _Context, ct: ComplexType) -> list[ComplexType]:
    """``ct`` first, then its extension bases (bounded, cycle-safe)."""
    chain = [ct]
    seen = {ct.id}
    current = ct
    while current.derivation == "extension" and current.base:
        base = ctx.lookup(ctx.complex_by_key, current.base)
        if base is None or base.id in seen:
            if base is None:
                # Everything the base contributed — including required
                # children — is silently absent from the output.
                ctx.note(
                    "extension_base_not_found", SCHEMA_INCOMPLETE, current.base, current
                )
            break
        chain.append(base)
        seen.add(base.id)
        current = base
    return chain


def _fill_complex(
    ctx: _Context,
    node: etree._Element,
    ct: ComplexType,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    chain = _base_chain(ctx, ct)
    # Attributes: bases first so the derived type's declarations win on clash.
    for member in reversed(chain):
        _fill_attributes(ctx, node, member.attributes, member.attribute_group_refs, set())
    if ctx.model.default_attributes and ct.default_attributes_apply:
        group = ctx.lookup(ctx.attr_group_by_key, ctx.model.default_attributes)
        if group is not None:
            _fill_attributes(ctx, node, group.attributes, group.attribute_group_refs, set())

    if ct.content_kind == "simple" or (ct.simple_content_base and not ct.particle):
        base_name = next((m.simple_content_base for m in chain if m.simple_content_base), None)
        facets = [f for m in chain for f in m.simple_content_facets]
        node.text = _value_for_type_name(ctx, base_name, facets)
        return
    if ct.derivation == "restriction" and ct.particle is None and ct.base:
        # A restriction that repeats nothing keeps the base's content.
        base = ctx.lookup(ctx.complex_by_key, ct.base)
        if base is not None and base.id not in type_stack:
            _fill_complex(ctx, node, base, depth=depth, type_stack=type_stack + (base.id,))
            return
        # The base is gone, or we are already inside it; either way the
        # restricted content model is missing from the output entirely.
        ctx.note(
            "restriction_base_not_found" if base is None else "restriction_base_recursive",
            SCHEMA_INCOMPLETE if base is None else GENERATOR_LIMIT,
            ct.base,
            ct,
        )
    if depth >= ctx.options.max_depth:
        node.append(etree.Comment(" depth limit reached "))
        ctx.note("depth_limit", GENERATOR_LIMIT, ct.name, ct)
        ctx.cuts += 1
        return
    # Content: bases first (extension appends), then the type's own particle.
    for member in reversed(chain):
        if member.particle is not None:
            _emit_particle(ctx, node, member.particle, depth=depth + 1, type_stack=type_stack)
    if ct.mixed and len(node) == 0 and not node.text:
        node.text = "text"


def _attribute_namespace(ctx: _Context, use: AttributeDecl, decl: AttributeDecl) -> str | None:
    if use.ref or decl.is_global:
        return decl.target_namespace or ctx.namespace_of(decl)
    if (decl.form or ctx.model.attribute_form_default) == "qualified":
        return ctx.namespace_of(decl)
    return None


def _fill_attributes(
    ctx: _Context,
    node: etree._Element,
    attributes: list[AttributeDecl],
    group_refs: list[str],
    seen_groups: set[str],
) -> None:
    for attribute in attributes:
        decl = attribute
        if attribute.ref:
            target = ctx.lookup(ctx.global_attribute_by_key, attribute.ref)
            if target is None:
                ctx.note(
                    "attribute_ref_not_found", SCHEMA_INCOMPLETE, attribute.ref, attribute
                )
                continue
            decl = target
        if attribute.use == "prohibited" or not decl.name:
            continue
        value = attribute.fixed or decl.fixed or attribute.default or decl.default
        if attribute.use != "required" and not ctx.options.include_optional and value is None:
            continue
        if value is None:
            if decl.type_inline is not None:
                value = _simple_value(ctx, decl.type_inline, ())
            else:
                value = _value_for_type_name(ctx, decl.type_name, [])
        namespace = _attribute_namespace(ctx, attribute, decl)
        if namespace:
            ctx.prefix_for(namespace)
        node.set(_tag(namespace, decl.name), value)
    for ref in group_refs:
        if ref in seen_groups:
            continue
        seen_groups.add(ref)
        group = ctx.lookup(ctx.attr_group_by_key, ref)
        if group is not None:
            _fill_attributes(ctx, node, group.attributes, group.attribute_group_refs, seen_groups)


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------


def _occurrences(ctx: _Context, particle: Particle) -> int:
    if particle.min_occurs > 0:
        return particle.min_occurs
    if not ctx.options.include_optional:
        return 0
    repeatable = particle.max_occurs == "unbounded" or particle.max_occurs > 1
    return ctx.options.repeat if repeatable else 1


def _emit_particle(
    ctx: _Context,
    parent: etree._Element,
    particle: Particle,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    count = _occurrences(ctx, particle)
    for _ in range(count):
        if particle.kind == "element" and particle.element is not None:
            _emit_element_particle(
                ctx,
                parent,
                particle.element,
                depth=depth,
                type_stack=type_stack,
                optional=particle.min_occurs == 0,
            )
        elif particle.kind in ("sequence", "all"):
            for child_particle in particle.children:
                _emit_particle(ctx, parent, child_particle, depth=depth, type_stack=type_stack)
        elif particle.kind == "choice":
            chosen = _pick_choice(particle.children)
            if chosen is not None:
                if chosen.kind != "element":
                    # No branch was a plain element, so we took a group or a
                    # wildcard — the weakest guess this generator makes.
                    ctx.note("choice_branch_not_element", GENERATOR_LIMIT, chosen.kind)
                forced = chosen if chosen.min_occurs > 0 else chosen.model_copy(update={"min_occurs": 1})
                _emit_particle(ctx, parent, forced, depth=depth, type_stack=type_stack)
        elif particle.kind == "group-ref":
            group = particle.group_inline
            if group is None and particle.group_ref:
                group = ctx.lookup(ctx.group_by_key, particle.group_ref)
            if group is None or group.particle is None:
                parent.append(etree.Comment(f" group {particle.group_ref} not found in schema "))
                ctx.note("group_not_found", SCHEMA_INCOMPLETE, particle.group_ref)
                continue
            _emit_particle(ctx, parent, group.particle, depth=depth, type_stack=type_stack)
        elif particle.kind == "any":
            parent.append(etree.Comment(" any element allowed here "))
            ctx.note("wildcard_skipped", GENERATOR_LIMIT, "xs:any")


def _emit_element_particle(
    ctx: _Context,
    parent: etree._Element,
    element: ElementDecl,
    *,
    depth: int,
    type_stack: tuple[str, ...],
    optional: bool = False,
) -> None:
    declaration = _deref_element(ctx, element)
    if declaration is None:
        parent.append(etree.Comment(f" element {element.ref} not found in schema "))
        ctx.note("element_ref_not_found", SCHEMA_INCOMPLETE, element.ref, element)
        return
    if declaration.abstract:
        substitute = _substitution_member(ctx, declaration)
        if substitute is None:
            parent.append(
                etree.Comment(f" abstract element {declaration.name}: no substitution found ")
            )
            ctx.note(
                "abstract_no_substitution", SCHEMA_INCOMPLETE, declaration.name, declaration
            )
            return
        declaration = substitute
    namespace = _element_namespace(ctx, declaration, is_root=bool(element.ref))
    if namespace:
        ctx.prefix_for(namespace)
    child = etree.SubElement(parent, _tag(namespace, declaration.name))
    if declaration.nillable and _is_empty_decl(declaration):
        child.set(f"{{{XSI_NS}}}nil", "true")
        return
    cuts_before = ctx.cuts
    notes_before = len(ctx.report)
    _fill_element(ctx, child, declaration, depth=depth, type_stack=type_stack)
    if optional and ctx.cuts > cuts_before:
        # Somewhere below, a required element hit the recursion or depth
        # guard and stayed empty; that would make the document invalid.
        # This occurrence is optional, so leave it out instead.
        parent.remove(child)
        parent.append(etree.Comment(f" optional {declaration.name} omitted (recursive or too deep) "))
        ctx.cuts = cuts_before
        # The subtree is gone, so its degradations no longer describe the
        # output; the one fact that survives is that we dropped it.
        del ctx.report[notes_before:]
        ctx.note("optional_subtree_dropped", GENERATOR_LIMIT, declaration.name, declaration)


def _pick_choice(children: list[Particle]) -> Particle | None:
    """First branch that is a plain element, else the first branch."""
    for child in children:
        if child.kind == "element":
            return child
    return children[0] if children else None


def _is_empty_decl(declaration: ElementDecl) -> bool:
    return (
        declaration.type_name is None
        and declaration.type_inline_complex is None
        and declaration.type_inline_simple is None
    )


def _substitution_member(ctx: _Context, head: ElementDecl) -> ElementDecl | None:
    for candidate in ctx.model.elements:
        if candidate.abstract or not candidate.substitution_group or not candidate.name:
            continue
        _, local = ctx.split_qname(candidate.substitution_group)
        if local == head.name:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Simple values
# ---------------------------------------------------------------------------


def _value_for_type_name(ctx: _Context, type_name: str | None, extra_facets: list[Facet]) -> str:
    if type_name is None:
        return _builtin_value(ctx, "string", extra_facets)
    resolved = _resolve_type(ctx, type_name)
    if resolved is None:
        # A string placeholder for a type we never saw: wrong whenever the
        # real type was numeric, a date, or an enumeration.
        ctx.note("type_placeholder_fallback", SCHEMA_INCOMPLETE, type_name)
        return _builtin_value(ctx, "string", extra_facets)
    kind, target = resolved
    if kind == "builtin":
        return _builtin_value(ctx, target, extra_facets)
    if kind == "simple":
        return _simple_value(ctx, target, (), extra_facets)
    if target.simple_content_base:
        return _value_for_type_name(
            ctx, target.simple_content_base, extra_facets + target.simple_content_facets
        )
    ctx.note("complex_type_as_text", GENERATOR_LIMIT, type_name)
    return _builtin_value(ctx, "string", extra_facets)


def _simple_value(
    ctx: _Context,
    simple: SimpleType,
    stack: tuple[str, ...],
    extra_facets: list[Facet] | None = None,
) -> str:
    if simple.id in stack:
        ctx.note("simple_recursion", GENERATOR_LIMIT, simple.name, simple)
        return "text"
    stack = stack + (simple.id,)
    facets = list(simple.facets) + list(extra_facets or [])
    if simple.derivation == "list":
        if simple.item_inline is not None:
            return _simple_value(ctx, simple.item_inline, stack)
        return _value_for_type_name(ctx, simple.item_type, [])
    if simple.derivation == "union":
        if simple.member_types:
            return _value_for_type_name(ctx, simple.member_types[0], facets)
        if simple.member_inline:
            return _simple_value(ctx, simple.member_inline[0], stack)
        ctx.note("union_without_members", SCHEMA_INCOMPLETE, simple.name, simple)
        return "text"
    # restriction / atomic: walk to the base, accumulating facets.
    if simple.base:
        resolved = _resolve_type(ctx, simple.base)
        if resolved is not None and resolved[0] == "builtin":
            return _builtin_value(ctx, resolved[1], facets)
        if resolved is not None and resolved[0] == "simple":
            return _simple_value(ctx, resolved[1], stack, facets)
        ctx.note("simple_base_not_found", SCHEMA_INCOMPLETE, simple.base, simple)
    return _builtin_value(ctx, "string", facets)


def _facet(facets: list[Facet], kind: str) -> str | None:
    for facet in facets:
        if facet.kind == kind:
            return facet.value
    return None


def _enumeration_value(local: str, facets: list[Facet]) -> str | None:
    """First enumeration value; for numbers, the first one inside the range facets."""
    values = [f.value for f in facets if f.kind == "enumeration"]
    if not values:
        return None
    if local not in _INTEGER_TYPES and local not in _DECIMAL_TYPES:
        return values[0]
    bounds = {k: _facet(facets, k) for k in ("minInclusive", "minExclusive", "maxInclusive", "maxExclusive")}

    def in_range(raw: str) -> bool:
        try:
            v = float(raw)
            lo_i, lo_e = bounds["minInclusive"], bounds["minExclusive"]
            hi_i, hi_e = bounds["maxInclusive"], bounds["maxExclusive"]
            return (
                (lo_i is None or v >= float(lo_i))
                and (lo_e is None or v > float(lo_e))
                and (hi_i is None or v <= float(hi_i))
                and (hi_e is None or v < float(hi_e))
            )
        except ValueError:
            return True

    return next((v for v in values if in_range(v)), values[0])


def _builtin_value(ctx: _Context, local: str, facets: list[Facet]) -> str:
    enum = _enumeration_value(local, facets)
    if enum is not None:
        return enum
    if local == "ID":
        return ctx.next_id()
    if local in _INTEGER_TYPES or local in _DECIMAL_TYPES:
        return _numeric_value(local, facets)
    if local not in _BUILTIN_VALUES:
        # Not a built-in we know: the value below is a guess.
        ctx.note("builtin_unknown", GENERATOR_LIMIT, local)
        return _string_value(ctx, local, facets)
    if local in _STRING_TYPES:
        return _string_value(ctx, local, facets)
    return _BUILTIN_VALUES[local]


def _numeric_value(local: str, facets: list[Facet]) -> str:
    integer = local in _INTEGER_TYPES
    fraction = _facet(facets, "fractionDigits")
    digits = int(fraction) if fraction and fraction.isdigit() else 1

    def fmt(value: float) -> str:
        if integer or digits == 0:
            return str(int(value))
        return f"{value:.{digits}f}"

    for kind in ("minInclusive", "minExclusive", "maxInclusive", "maxExclusive"):
        raw = _facet(facets, kind)
        if raw is None:
            continue
        try:
            number = float(raw)
        except ValueError:
            continue
        if kind == "minExclusive":
            number += 1
        elif kind == "maxExclusive":
            number -= 1
        if kind.startswith("max") and number > 0:
            # Prefer the smallest sensible value below the maximum.
            number = min(number, 1 if integer else 0.0)
        return fmt(number)
    return fmt(float(_BUILTIN_VALUES.get(local, "1")))


def _string_value(ctx: _Context, local: str, facets: list[Facet]) -> str:
    pattern = _facet(facets, "pattern")
    if pattern is not None:
        sample = sample_from_pattern(pattern)
        if sample is not None:
            return sample
        # We could not read the pattern, so the placeholder below will almost
        # certainly violate it — a prime source of invalid samples.
        ctx.note("pattern_unsupported", GENERATOR_LIMIT, pattern)
    base = _BUILTIN_VALUES.get(local, "string")
    length = _facet(facets, "length") or _facet(facets, "minLength")
    max_length = _facet(facets, "maxLength")
    if length and length.isdigit():
        n = int(length)
        return (base * (n // max(len(base), 1) + 1))[:n] if n > 0 else ""
    if max_length and max_length.isdigit():
        return base[: int(max_length)]
    return base
