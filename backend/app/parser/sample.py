"""Generate a skeleton XML instance for an element of a parsed schema.

The generator walks the content model the way XMLSpy's "Generate Sample XML"
does: required particles once, the first branch of a choice, the first
enumeration value, type-appropriate placeholders for built-in types, and a
best-effort string for ``xs:pattern`` facets. Optional content is included
on request. Identity constraints (xs:key, xs:keyref, xs:unique) are settled
on the finished tree, since their selectors are XPath; assertions are not
evaluated. It never raises on an incomplete schema: unresolved references
become XML comments so the user can see what could not be filled in.
"""

from __future__ import annotations

import base64
import itertools
import re
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from functools import lru_cache
from typing import TypeVar
from xml.sax.saxutils import quoteattr

from lxml import etree

from app.parser.model import (
    AttributeDecl,
    AttributeGroup,
    ComplexType,
    ElementDecl,
    Facet,
    Group,
    IdentityConstraint,
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
    # Elements after which optional content is no longer added. Wide optional
    # fan-out (JATS) otherwise grows to hundreds of thousands of elements.
    max_elements: int = 10_000


Key = tuple[str | None, str]


@dataclass(slots=True)
class _FileSettings:
    """What one schema document's root element says about the names inside it.

    The model only keeps the main file's elementFormDefault and one merged
    prefix map, which is wrong for every imported file that differs (SIRI:
    an unqualified main file importing qualified ones with their own default
    namespace).
    """

    element_form: str
    attribute_form: str
    prefixes: dict[str, str]
    # Present only when the file declares xmlns="..." on its root.
    default_namespace: str | None
    has_default_namespace: bool


_MARKUP_NOISE = re.compile(r"<!--.*?-->|<\?.*?\?>", re.S)
_SCHEMA_START = re.compile(r"<(?:[\w.-]+:)?schema\b(.*?)>", re.S)
_ATTRIBUTE = re.compile(r"""([\w.:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_FILE_SETTINGS_CACHE: dict[tuple[str, int, str, str], _FileSettings | None] = {}


def _file_settings(file_id: str, content: str | None) -> _FileSettings | None:
    if not content:
        return None
    # A cheap key: re-reading a 15 MB taxonomy on every sample is not.
    key = (file_id, len(content), content[:256], content[-256:])
    if key in _FILE_SETTINGS_CACHE:
        return _FILE_SETTINGS_CACHE[key]
    settings = None
    match = _SCHEMA_START.search(_MARKUP_NOISE.sub("", content[:200_000]))
    if match is not None:
        attributes = {
            m.group(1): m.group(2) if m.group(2) is not None else m.group(3)
            for m in _ATTRIBUTE.finditer(match.group(1))
        }
        settings = _FileSettings(
            element_form=attributes.get("elementFormDefault", "unqualified"),
            attribute_form=attributes.get("attributeFormDefault", "unqualified"),
            prefixes={k[len("xmlns:"):]: v for k, v in attributes.items() if k.startswith("xmlns:")},
            default_namespace=attributes.get("xmlns"),
            has_default_namespace="xmlns" in attributes,
        )
    if len(_FILE_SETTINGS_CACHE) > 4096:
        _FILE_SETTINGS_CACHE.clear()
    _FILE_SETTINGS_CACHE[key] = settings
    return settings


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
    # Elements created so far, and whether optional content was cut because of it.
    emitted: int = 0
    budget_hit: bool = False
    # Declarations being filled right now, so a wildcard does not pick an ancestor.
    open_elements: list[str] = field(default_factory=list)
    # Prefixes used inside attribute values (xsi:type), which cleanup must keep.
    value_prefixes: set[str] = field(default_factory=set)
    derived_types: dict[str, ComplexType | None] = field(default_factory=dict)
    wildcard_members: dict[str, list[ElementDecl]] = field(default_factory=dict)
    file_settings: dict[str, _FileSettings] = field(default_factory=dict)
    # Files whose declarations are being expanded, innermost last. Particles
    # carry no source location, so their QNames resolve in this file.
    file_stack: list[str | None] = field(default_factory=list)
    # Minimal content cost per declaration id, for choosing choice branches.
    costs: dict[object, tuple[float, frozenset[str]]] = field(default_factory=dict)
    cost_steps: int = 0
    # Substitution-group members by the (namespace, name) of their head; built on first use.
    members_by_head: dict[Key, list[ElementDecl]] | None = None
    # For identity constraints: elements that declare them, optional
    # occurrences that may be dropped, and how each value was produced
    # (built-in type and facets, keyed by element and attribute name).
    constraint_scopes: list[tuple[etree._Element, ElementDecl]] = field(default_factory=list)
    optional_nodes: set[etree._Element] = field(default_factory=set)
    value_specs: dict[tuple[etree._Element, str | None], tuple[str, list[Facet]]] = field(
        default_factory=dict
    )
    last_spec: tuple[str, list[Facet]] | None = None
    xpaths: dict[tuple[str, str], etree.XPath] = field(default_factory=dict)
    unusable_constraints: set[str] = field(default_factory=set)

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

    def file_of(self, decl: object | None) -> str | None:
        """The file a QName written on ``decl`` resolves in."""
        ref = getattr(decl, "source_ref", None) if decl is not None else None
        if ref is not None:
            return ref.file_id
        return self.file_stack[-1] if self.file_stack else None

    def settings_of(self, decl: object | None) -> _FileSettings | None:
        file_id = self.file_of(decl)
        return self.file_settings.get(file_id) if file_id is not None else None

    def namespace_of_prefix(self, prefix: str | None, file_id: str | None = None) -> str | None:
        settings = self.file_settings.get(file_id) if file_id is not None else None
        if prefix is None:
            if settings is not None and settings.has_default_namespace:
                return settings.default_namespace or None
            # No default namespace in sight: the file's own target namespace is
            # the best guess (and what a chameleon include means).
            return self.declared_namespace(file_id)
        if settings is not None and prefix in settings.prefixes:
            return settings.prefixes[prefix]
        return self.model.namespaces.get(prefix)

    def split_qname(self, qname: str, owner: object | None = None) -> Key:
        if qname.startswith("{"):
            ns, _, local = qname[1:].partition("}")
            return ns, local
        file_id = self.file_of(owner)
        prefix, sep, local = qname.rpartition(":")
        if not sep:
            return self.namespace_of_prefix(None, file_id), qname
        return self.namespace_of_prefix(prefix, file_id), local

    def lookup_exact(self, table: dict[Key, T], qname: str, owner: object | None = None) -> T | None:
        """Only a real ``(namespace, name)`` hit — no local-name guessing."""
        return table.get(self.split_qname(qname, owner))

    def lookup_loose(self, table: dict[Key, T], qname: str) -> T | None:
        """The local name alone, in any namespace (prefix undeclared / chameleon include)."""
        _, local = self.split_qname(qname)
        for (_, name), value in table.items():
            if name == local:
                return value
        return None

    def lookup(self, table: dict[Key, T], qname: str, owner: object | None = None) -> T | None:
        hit = self.lookup_exact(table, qname, owner)
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
    ctx: _Context, type_name: str, decl: object | None = None, *, quiet: bool = False
) -> tuple[str, str] | tuple[str, SimpleType] | tuple[str, ComplexType] | None:
    """Classify a type reference: ("builtin", local) | ("simple", st) | ("complex", ct).

    The QName resolves in the file ``decl`` was written in -- its prefixes
    and default namespace -- falling back to the merged prefix map. An
    unprefixed name that matches none of the schema's types is tried as the
    built-in type of that name.

    Both tables are searched exactly *before* either is searched by local name:
    the local-name fallback is a guess for undeclared prefixes and chameleon
    includes, and letting it run inside the simpleType lookup first let a
    same-named simpleType in any other namespace beat the correctly referenced
    complexType — which put a text placeholder into an element-only element.
    ``quiet`` skips the report, for lookups that only estimate.
    """
    ns, local = ctx.split_qname(type_name, decl)
    if ns == XSD_NS:
        return ("builtin", local)
    simple = ctx.lookup_exact(ctx.simple_by_key, type_name, decl)
    if simple is not None:
        return ("simple", simple)
    complex_type = ctx.lookup_exact(ctx.complex_by_key, type_name, decl)
    if complex_type is not None:
        return ("complex", complex_type)
    if ":" not in type_name and not type_name.startswith("{") and local in _BUILTIN_VALUES:
        return ("builtin", local)
    # Nothing matched exactly; guess by local name, and say that we guessed.
    simple = ctx.lookup_loose(ctx.simple_by_key, type_name)
    complex_type = None if simple is not None else ctx.lookup_loose(ctx.complex_by_key, type_name)
    if simple is None and complex_type is None:
        return None
    if not quiet:
        ctx.note("type_resolved_by_local_name", GENERATOR_LIMIT, type_name, decl)
    return ("simple", simple) if simple is not None else ("complex", complex_type)


def _build_context(model: SchemaModel, options: SampleOptions) -> _Context:
    ctx = _Context(model=model, options=options)
    ctx.file_namespaces = {f.id: f.target_namespace for f in model.files}
    for source in model.files:
        settings = _file_settings(source.id, source.content)
        if settings is not None:
            ctx.file_settings[source.id] = settings
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
    declaration = _deref_element(ctx, element)
    root = (
        _unresolved_root(ctx, element) if declaration is None else _generated_root(ctx, declaration)
    )
    # Declare the prefixes we used (and only those) on the root.
    nsmap = dict(ctx.nsmap)
    xsi_attributes = (f"{{{XSI_NS}}}nil", f"{{{XSI_NS}}}type")
    if any(key in el.attrib for el in root.iter(etree.Element) for key in xsi_attributes):
        nsmap["xsi"] = XSI_NS
    if nsmap:
        new_root = etree.Element(root.tag, nsmap=nsmap)
        for key, value in root.attrib.items():
            new_root.set(key, value)
        new_root.text = root.text
        for child in list(root):
            new_root.append(child)
        root = new_root
    etree.cleanup_namespaces(root, keep_ns_prefixes=sorted(ctx.value_prefixes))
    document = etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    ).decode("utf-8")
    return document, SampleReport(entries=ctx.report)


def _generated_root(ctx: _Context, element: ElementDecl) -> etree._Element:
    """The document element for a resolved declaration, filled in."""
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
    ctx.emitted = 1
    ctx.open_elements.append(element.id)
    if element.identity_constraints:
        ctx.constraint_scopes.append((root, element))
    _fill_element(ctx, root, element, depth=0, type_stack=())
    _apply_identity_constraints(ctx, root)
    if ctx.budget_hit:
        ctx.note("size_limit", GENERATOR_LIMIT, element.name, element)
    return root


def _unresolved_root(ctx: _Context, element: ElementDecl) -> etree._Element:
    """A root for a ref whose target never loaded (a missing import).

    It keeps the name it was referenced by -- the anonymous ``<element/>`` it
    used to become told the user nothing (UBL cac:*) -- and says what is
    missing, the way the same ref does as a child.
    """
    namespace, local = ctx.split_qname(element.ref or "", element)
    if namespace:
        ctx.prefix_for(namespace)
    root = etree.Element(_tag(namespace, local))
    root.append(etree.Comment(f" element {element.ref} not found in schema "))
    ctx.note("element_ref_not_found", SCHEMA_INCOMPLETE, element.ref, element)
    return root


def _tag(namespace: str | None, name: str | None) -> str:
    local = name or "element"
    return f"{{{namespace}}}{local}" if namespace else local


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------


def _deref_element(ctx: _Context, element: ElementDecl) -> ElementDecl | None:
    if not element.ref:
        return element
    return ctx.lookup(ctx.global_element_by_key, element.ref, element)


def _element_namespace(ctx: _Context, element: ElementDecl, *, is_root: bool) -> str | None:
    if element.target_namespace:
        return element.target_namespace
    if element.is_global or is_root:
        return ctx.namespace_of(element)
    settings = ctx.settings_of(element)
    form = element.form or (settings.element_form if settings else ctx.model.element_form_default)
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
            else _recorded(ctx, node, None, _simple_value, ctx, element.type_inline_simple, ())
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
        node.text = (
            element.default
            if element.default is not None
            else _recorded(ctx, node, None, _builtin_value, ctx, target, [])
        )
    elif kind == "simple":
        node.text = (
            element.default
            if element.default is not None
            else _recorded(ctx, node, None, _simple_value, ctx, target, ())
        )
    else:
        if target.abstract:
            derived = _derived_type(ctx, target)
            if derived is None:
                node.append(etree.Comment(f" abstract type {element.type_name}: no derived type found "))
                ctx.note("abstract_type_without_derivation", SCHEMA_INCOMPLETE, element.type_name, element)
                # Nothing valid can go here, so an optional occurrence is dropped (UCI ExtensionData).
                ctx.cuts += 1
                return
            # An element of an abstract type has to name a concrete one (Garmin TCX).
            node.set(f"{{{XSI_NS}}}type", _type_qname(ctx, derived))
            target = derived
        if target.id in type_stack:
            node.append(etree.Comment(f" recursive {element.type_name} omitted "))
            ctx.note("recursion_cut", GENERATOR_LIMIT, element.type_name, element)
            ctx.cuts += 1
            return
        _fill_complex(ctx, node, target, depth=depth, type_stack=type_stack + (target.id,))


# ---------------------------------------------------------------------------
# Complex types
# ---------------------------------------------------------------------------


def _base_chain(ctx: _Context, ct: ComplexType, *, quiet: bool = False) -> list[ComplexType]:
    """``ct`` first, then its extension bases (bounded, cycle-safe)."""
    chain = [ct]
    seen = {ct.id}
    current = ct
    while current.derivation == "extension" and current.base:
        base = ctx.lookup(ctx.complex_by_key, current.base, current)
        if base is None or base.id in seen:
            # A simpleContent extension of a simple or built-in type has no
            # complexType base; its value comes from simple_content_base.
            if base is None and not current.simple_content_base and not quiet:
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


def _attribute_chain(ctx: _Context, ct: ComplexType) -> list[ComplexType]:
    """``ct`` first, then every complex base it derives from.

    Unlike content, attribute uses are inherited through restriction too: a
    restriction only redeclares or prohibits them (XBRL linkbase types).
    """
    chain = [ct]
    seen = {ct.id}
    current = ct
    while current.derivation in ("extension", "restriction") and current.base:
        base = ctx.lookup(ctx.complex_by_key, current.base, current)
        if base is None or base.id in seen:
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
    for member in reversed(_attribute_chain(ctx, ct)):
        _fill_attributes(ctx, node, member.attributes, member.attribute_group_refs, set(), member)
    if ctx.model.default_attributes and ct.default_attributes_apply:
        group = ctx.lookup(ctx.attr_group_by_key, ctx.model.default_attributes)
        if group is not None:
            _fill_attributes(ctx, node, group.attributes, group.attribute_group_refs, set(), group)

    # Simple content may sit further down the extension chain: a complexContent
    # extension that only adds attributes keeps its base's text (GLEIF
    # OtherEntityNameType over NameType).
    if not any(m.particle for m in chain) and any(
        m.content_kind == "simple" or m.simple_content_base for m in chain
    ):
        owner = next((m for m in chain if m.simple_content_base), None)
        facets = [f for m in chain for f in m.simple_content_facets]
        base_name = owner.simple_content_base if owner else None
        node.text = _recorded(ctx, node, None, _value_for_type_name, ctx, base_name, facets, owner)
        return
    if ct.derivation == "restriction" and ct.particle is None and ct.base:
        # A restriction that repeats nothing keeps the base's content.
        base = ctx.lookup(ctx.complex_by_key, ct.base, ct)
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
            ctx.file_stack.append(ctx.file_of(member))
            try:
                _emit_particle(ctx, node, member.particle, depth=depth + 1, type_stack=type_stack)
            finally:
                ctx.file_stack.pop()
    if ct.mixed and len(node) == 0 and not node.text:
        node.text = "text"


def _attribute_namespace(ctx: _Context, use: AttributeDecl, decl: AttributeDecl) -> str | None:
    if use.ref or decl.is_global:
        return decl.target_namespace or ctx.namespace_of(decl)
    settings = ctx.settings_of(decl)
    form = decl.form or (settings.attribute_form if settings else ctx.model.attribute_form_default)
    if form == "qualified":
        return ctx.namespace_of(decl)
    return None


def _fill_attributes(
    ctx: _Context,
    node: etree._Element,
    attributes: list[AttributeDecl],
    group_refs: list[str],
    seen_groups: set[str],
    owner: object | None = None,
) -> None:
    for attribute in attributes:
        decl = attribute
        if attribute.ref:
            target = ctx.lookup(ctx.global_attribute_by_key, attribute.ref, attribute)
            if target is None:
                ctx.note(
                    "attribute_ref_not_found", SCHEMA_INCOMPLETE, attribute.ref, attribute
                )
                continue
            decl = target
        if not decl.name:
            continue
        namespace = _attribute_namespace(ctx, attribute, decl)
        if attribute.use == "prohibited":
            # A restriction taking back an attribute its base declared.
            node.attrib.pop(_tag(namespace, decl.name), None)
            continue
        value = attribute.fixed or decl.fixed or attribute.default or decl.default
        if attribute.use != "required" and not ctx.options.include_optional and value is None:
            continue
        tag = _tag(namespace, decl.name)
        if value is None:
            if decl.type_inline is not None:
                value = _recorded(ctx, node, tag, _simple_value, ctx, decl.type_inline, ())
            else:
                value = _recorded(ctx, node, tag, _value_for_type_name, ctx, decl.type_name, [], decl)
        if namespace:
            ctx.prefix_for(namespace)
        node.set(tag, value)
    for ref in group_refs:
        if ref in seen_groups:
            continue
        seen_groups.add(ref)
        group = ctx.lookup(ctx.attr_group_by_key, ref, owner)
        if group is not None:
            _fill_attributes(ctx, node, group.attributes, group.attribute_group_refs, seen_groups, group)


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------


def _occurrences(ctx: _Context, particle: Particle) -> int:
    if particle.max_occurs == 0:
        # maxOccurs="0" takes the particle out of the content model (goAML).
        return 0
    if particle.min_occurs > 0:
        return particle.min_occurs
    if not ctx.options.include_optional:
        return 0
    if ctx.emitted >= ctx.options.max_elements:
        ctx.budget_hit = True
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
            chosen = _pick_choice(ctx, particle.children, type_stack)
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
            ctx.file_stack.append(ctx.file_of(group))
            try:
                _emit_particle(ctx, parent, group.particle, depth=depth, type_stack=type_stack)
            finally:
                ctx.file_stack.pop()
        elif particle.kind == "any":
            if particle.min_occurs > 0:
                _emit_wildcard(ctx, parent, particle, depth=depth, type_stack=type_stack)
                continue
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
    ctx.emitted += 1
    if optional:
        ctx.optional_nodes.add(child)
    if declaration.identity_constraints:
        ctx.constraint_scopes.append((child, declaration))
    if declaration.nillable and _is_empty_decl(declaration):
        child.set(f"{{{XSI_NS}}}nil", "true")
        return
    cuts_before = ctx.cuts
    notes_before = len(ctx.report)
    ctx.open_elements.append(declaration.id)
    try:
        _fill_element(ctx, child, declaration, depth=depth, type_stack=type_stack)
    finally:
        ctx.open_elements.pop()
    if optional and ctx.cuts > cuts_before:
        # Somewhere below, a required element hit the recursion or depth
        # guard, or had an abstract type nothing derives from, and stayed
        # empty; that would make the document invalid. This occurrence is
        # optional, so leave it out instead.
        parent.remove(child)
        parent.append(
            etree.Comment(f" optional {declaration.name} omitted: its content cannot be generated ")
        )
        ctx.cuts = cuts_before
        # The subtree is gone, so its degradations no longer describe the
        # output; the one fact that survives is that we dropped it.
        del ctx.report[notes_before:]
        ctx.note("optional_subtree_dropped", GENERATOR_LIMIT, declaration.name, declaration)


def _pick_choice(
    ctx: _Context, children: list[Particle], type_stack: tuple[str, ...] = ()
) -> Particle | None:
    """A branch that can end, preferring a plain element, then document order.

    A branch that can only be completed by nesting an element or type we are
    already inside never terminates (JATS: alternatives > array > alternatives),
    so it is taken only when every branch is like that.
    """
    usable = [child for child in children if child.max_occurs != 0]
    if not usable:
        return None
    open_ids = frozenset(ctx.open_elements) | frozenset(type_stack)
    ctx.cost_steps = 0
    try:
        endless = [_occurrence_cost(ctx, child, open_ids, 0)[0] == _ENDLESS for child in usable]
    except _CostBudgetExceededError:
        endless = [False] * len(usable)
    ranked = sorted(range(len(usable)), key=lambda i: (endless[i], usable[i].kind != "element", i))
    return usable[ranked[0]]


_ENDLESS = float("inf")
_COST_DEPTH = 64
_COST_STEPS = 20_000


class _CostBudgetExceededError(Exception):
    pass


def _required_cost(
    ctx: _Context, particle: Particle, visiting: frozenset[str], depth: int
) -> tuple[float, frozenset[str]]:
    if particle.max_occurs == 0 or particle.min_occurs == 0:
        return 0, frozenset()
    cost, hits = _occurrence_cost(ctx, particle, visiting, depth)
    return cost * particle.min_occurs, hits


def _occurrence_cost(
    ctx: _Context, particle: Particle, visiting: frozenset[str], depth: int
) -> tuple[float, frozenset[str]]:
    """Elements one occurrence of ``particle`` needs at least, and which open ids that relied on.

    ``hits`` names the members of ``visiting`` an endless result ran into; a
    result without hits does not depend on where we are and can be cached.
    """
    if particle.kind == "element" and particle.element is not None:
        return _element_cost(ctx, particle.element, visiting, depth)
    if particle.kind in ("sequence", "all"):
        total, hits = 0.0, frozenset()
        for child in particle.children:
            cost, child_hits = _required_cost(ctx, child, visiting, depth)
            total, hits = total + cost, hits | child_hits
        return total, hits
    if particle.kind == "choice":
        best, hits = _ENDLESS, frozenset()
        for child in particle.children:
            if child.max_occurs == 0:
                continue
            cost, child_hits = _occurrence_cost(ctx, child, visiting, depth)
            hits |= child_hits
            best = min(best, cost)
        return (best, hits) if best == _ENDLESS else (best, frozenset())
    if particle.kind == "group-ref":
        group = particle.group_inline
        if group is None and particle.group_ref:
            group = ctx.lookup(ctx.group_by_key, particle.group_ref)
        if group is None or group.particle is None:
            return 0, frozenset()
        return _required_cost(ctx, group.particle, visiting, depth)
    return 1, frozenset()


def _element_cost(
    ctx: _Context, element: ElementDecl, visiting: frozenset[str], depth: int
) -> tuple[float, frozenset[str]]:
    ctx.cost_steps += 1
    if ctx.cost_steps > _COST_STEPS:
        raise _CostBudgetExceededError
    declaration = _deref_element(ctx, element)
    if declaration is not None and declaration.abstract:
        declaration = _substitution_member(ctx, declaration)
    if declaration is None:
        return 1, frozenset()
    if declaration.id in visiting:
        return _ENDLESS, frozenset({declaration.id})
    if depth >= _COST_DEPTH:
        return _ENDLESS, frozenset({declaration.id})
    cached = ctx.costs.get(declaration.id)
    if cached is not None:
        return cached
    cost, hits = _declaration_content_cost(ctx, declaration, visiting | {declaration.id}, depth + 1)
    result = (1 + cost, hits - {declaration.id})
    if not result[1]:
        ctx.costs[declaration.id] = result
    return result


def _declaration_content_cost(
    ctx: _Context, declaration: ElementDecl, visiting: frozenset[str], depth: int
) -> tuple[float, frozenset[str]]:
    if declaration.fixed is not None or declaration.type_inline_simple is not None:
        return 0, frozenset()
    complex_type = declaration.type_inline_complex
    if complex_type is None and declaration.type_name:
        resolved = _resolve_type(ctx, declaration.type_name, declaration, quiet=True)
        if resolved is None or resolved[0] != "complex":
            return 0, frozenset()
        complex_type = resolved[1]
        if complex_type.abstract:
            complex_type = _derived_type(ctx, complex_type) or complex_type
    if complex_type is None:
        return 0, frozenset()
    if complex_type.id in visiting:
        return _ENDLESS, frozenset({complex_type.id})
    inner = visiting | {complex_type.id}
    if complex_type.content_kind == "simple" or (
        complex_type.simple_content_base and not complex_type.particle
    ):
        return 0, frozenset()
    total, hits = 0.0, frozenset()
    for member in _base_chain(ctx, complex_type, quiet=True):
        if member.particle is not None:
            cost, member_hits = _required_cost(ctx, member.particle, inner, depth)
            total, hits = total + cost, hits | member_hits
    return total, hits - {complex_type.id}


def _is_empty_decl(declaration: ElementDecl) -> bool:
    return (
        declaration.type_name is None
        and declaration.type_inline_complex is None
        and declaration.type_inline_simple is None
    )


def _derived_type(ctx: _Context, base: ComplexType) -> ComplexType | None:
    """First concrete named complexType derived, directly or not, from ``base``."""
    if base.id in ctx.derived_types:
        return ctx.derived_types[base.id]
    found = None
    for candidate in ctx.model.complex_types:
        if candidate.abstract or not candidate.name or candidate.id == base.id:
            continue
        current, seen = candidate, {candidate.id}
        while current.base and found is None:
            parent = ctx.lookup(ctx.complex_by_key, current.base, current)
            if parent is None or parent.id in seen:
                break
            if parent.id == base.id:
                found = candidate
            seen.add(parent.id)
            current = parent
        if found is not None:
            break
    ctx.derived_types[base.id] = found
    return found


def _type_qname(ctx: _Context, complex_type: ComplexType) -> str:
    namespace = ctx.namespace_of(complex_type)
    if not namespace:
        return complex_type.name or ""
    prefix = ctx.prefix_for(namespace)
    ctx.value_prefixes.add(prefix)
    return f"{prefix}:{complex_type.name}"


# Namespace of the made-up element that fills a lax or skip wildcard.
_FOREIGN_NAMESPACE = "urn:example:any"


def _wildcard_allows(constraint: str | None, namespace: str | None, target: str | None) -> bool:
    tokens = (constraint or "##any").split()
    if tokens == ["##any"]:
        return True
    if tokens == ["##other"]:
        # XSD 1.0: any namespace except the target one, and never no namespace.
        return namespace is not None and namespace != target
    allowed = {target if t == "##targetNamespace" else None if t == "##local" else t for t in tokens}
    return namespace in allowed


def _emit_wildcard(
    ctx: _Context,
    parent: etree._Element,
    particle: Particle,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    """Fill a mandatory xs:any, which used to stay empty (XBRL segment).

    A lax or skip wildcard takes a made-up element from an allowed namespace;
    a strict one needs a global declaration, so one is picked from the schema.
    """
    constraint = particle.wildcard_namespace
    target = ctx.model.target_namespace
    if particle.wildcard_process_contents in ("lax", "skip"):
        first = (constraint or "##any").split()[0]
        namespace = {
            "##any": _FOREIGN_NAMESPACE,
            "##other": _FOREIGN_NAMESPACE,
            "##targetNamespace": target,
            "##local": None,
        }.get(first, first)
        if _wildcard_allows(constraint, namespace, target):
            if namespace:
                ctx.prefix_for(namespace)
            etree.SubElement(parent, _tag(namespace, "any"))
            ctx.emitted += 1
            return
    members = _wildcard_members(ctx, constraint)
    member = next((m for m in members if m.id not in ctx.open_elements), None)
    if member is None:
        parent.append(etree.Comment(" any element allowed here "))
        if members:
            # Only the elements we are inside match; nesting one would recurse.
            ctx.note("wildcard_skipped", GENERATOR_LIMIT, "xs:any")
        else:
            ctx.note("wildcard_without_declaration", SCHEMA_INCOMPLETE, constraint or "##any")
        return
    _emit_element_particle(ctx, parent, member, depth=depth, type_stack=type_stack)


def _wildcard_members(ctx: _Context, constraint: str | None) -> list[ElementDecl]:
    """Concrete global elements a strict wildcard accepts, in document order."""
    key = constraint or "##any"
    if key not in ctx.wildcard_members:
        target = ctx.model.target_namespace
        ctx.wildcard_members[key] = [
            element
            for element in ctx.model.elements
            if element.name
            and not element.abstract
            and _wildcard_allows(constraint, element.target_namespace or ctx.namespace_of(element), target)
        ]
    return ctx.wildcard_members[key]


def _substitution_member(ctx: _Context, head: ElementDecl) -> ElementDecl | None:
    """The nearest concrete element that may stand in for ``head``.

    Substitution groups are transitive, and their middle layers are often
    abstract themselves (SIRI: AbstractServiceRequest >
    AbstractFunctionalServiceRequest > StopMonitoringRequest), so the search
    goes through abstract members, level by level.
    """
    queue, seen = [head], {head.id}
    while queue:
        current = queue.pop(0)
        for candidate in _direct_members(ctx, current):
            if candidate.id in seen:
                continue
            seen.add(candidate.id)
            if not candidate.abstract:
                return candidate
            queue.append(candidate)
    return None


def _direct_members(ctx: _Context, head: ElementDecl) -> list[ElementDecl]:
    if ctx.members_by_head is None:
        ctx.members_by_head = {}
        for candidate in ctx.model.elements:
            if candidate.name and candidate.substitution_group:
                key = ctx.split_qname(candidate.substitution_group, candidate)
                ctx.members_by_head.setdefault(key, []).append(candidate)
    exact = ctx.members_by_head.get((head.target_namespace or ctx.namespace_of(head), head.name or ""))
    if exact:
        return exact
    # An undeclared prefix or a chameleon include: match the local name alone.
    return [m for (_, local), members in ctx.members_by_head.items() if local == head.name for m in members]


# ---------------------------------------------------------------------------
# Identity constraints
# ---------------------------------------------------------------------------


class _UnusableConstraintError(Exception):
    """A selector or field this generator cannot evaluate."""


def _apply_identity_constraints(ctx: _Context, root: etree._Element) -> None:
    """Settle xs:key, xs:unique and xs:keyref on the finished tree.

    Without this every occurrence carried the same placeholder, so keys and
    uniques collided (XTCE) and keyrefs pointed at nothing (Garmin TCX).
    Three passes, in order: drop optional nodes a key selects but that lack
    a field, make key and unique tuples distinct, then point every keyref at
    an existing tuple of its key.
    """
    if not ctx.constraint_scopes:
        return
    scopes = list(ctx.constraint_scopes)
    for step in (_drop_incomplete_key_targets, _make_distinct, _resolve_keyref):
        for scope, declaration in scopes:
            if not _in_tree(scope, root):
                continue
            for constraint in declaration.identity_constraints:
                if constraint.id in ctx.unusable_constraints:
                    continue
                try:
                    step(ctx, root, scope, constraint, scopes)
                except _UnusableConstraintError:
                    ctx.unusable_constraints.add(constraint.id)
                    ctx.note("identity_constraint_skipped", GENERATOR_LIMIT, constraint.name, constraint)


def _in_tree(node: etree._Element, root: etree._Element) -> bool:
    return node is root or any(ancestor is root for ancestor in node.iterancestors())


def _run_xpath(ctx: _Context, constraint: IdentityConstraint, expression: str, node: etree._Element) -> list:
    if constraint.xpath_default_namespace:
        raise _UnusableConstraintError  # XPath 1.0 has no default namespace for name tests
    key = (constraint.id, expression)
    xpath = ctx.xpaths.get(key)
    if xpath is None:
        namespaces = {prefix: uri for prefix, uri in ctx.model.namespaces.items() if prefix}
        settings = ctx.settings_of(constraint)
        if settings is not None:
            namespaces.update({prefix: uri for prefix, uri in settings.prefixes.items() if prefix})
        try:
            xpath = etree.XPath(expression.strip(), namespaces=namespaces)
        except etree.XPathError as exc:
            raise _UnusableConstraintError from exc
        ctx.xpaths[key] = xpath
    try:
        result = xpath(node)
    except etree.XPathError as exc:
        raise _UnusableConstraintError from exc
    return result if isinstance(result, list) else []


def _select(ctx: _Context, constraint: IdentityConstraint, scope: etree._Element) -> list[etree._Element]:
    selected = _run_xpath(ctx, constraint, constraint.selector, scope)
    return [node for node in selected if isinstance(node, etree._Element)]


def _fields(ctx: _Context, constraint: IdentityConstraint, target: etree._Element) -> list[object] | None:
    """One node per field, or None when a field reaches nothing (or more than one node)."""
    hits = []
    for expression in constraint.fields:
        result = _run_xpath(ctx, constraint, expression, target)
        if len(result) != 1:
            return None
        hits.append(result[0])
    return hits


def _hit_value(hit: object) -> str:
    return (hit.text or "") if isinstance(hit, etree._Element) else str(hit)


def _slot(hit: object) -> tuple[etree._Element, str | None] | None:
    """Where a field's value lives: an element's text or one of its attributes."""
    if isinstance(hit, etree._Element):
        return (hit, None) if len(hit) == 0 else None
    if getattr(hit, "is_attribute", False):
        parent = hit.getparent()
        return (parent, hit.attrname) if parent is not None else None
    return None


def _write(slot: tuple[etree._Element, str | None], value: str) -> None:
    element, attribute = slot
    if attribute is None:
        element.text = value
    else:
        element.set(attribute, value)


def _removable(ctx: _Context, node: etree._Element, root: etree._Element) -> etree._Element | None:
    """The node itself or its nearest ancestor that was emitted as an optional occurrence."""
    current = node
    while current is not None and current is not root:
        if current in ctx.optional_nodes:
            return current
        current = current.getparent()
    return None


def _drop(ctx: _Context, node: etree._Element) -> None:
    parent = node.getparent()
    name = etree.QName(node).localname
    parent.insert(
        parent.index(node), etree.Comment(f" optional {name} omitted: it would break an identity constraint ")
    )
    parent.remove(node)
    ctx.note("optional_subtree_dropped", GENERATOR_LIMIT, name)


def _drop_incomplete_key_targets(
    ctx: _Context, root: etree._Element, scope: etree._Element, constraint: IdentityConstraint, _scopes: list
) -> None:
    """Every node a key selects needs every field (XTCE: MessageSet/* also reaches LongDescription)."""
    if constraint.kind != "key":
        return
    for target in _select(ctx, constraint, scope):
        if not _in_tree(target, root) or _fields(ctx, constraint, target) is not None:
            continue
        removable = _removable(ctx, target, root)
        if removable is None:
            ctx.note("key_field_missing", GENERATOR_LIMIT, constraint.name, constraint)
        else:
            _drop(ctx, removable)


def _make_distinct(
    ctx: _Context, root: etree._Element, scope: etree._Element, constraint: IdentityConstraint, _scopes: list
) -> None:
    if constraint.kind not in ("key", "unique"):
        return
    taken: set[tuple[str, ...]] = set()
    for target in _select(ctx, constraint, scope):
        hits = _fields(ctx, constraint, target)
        if hits is None:
            continue  # a unique may leave fields out; keys were settled in the pass before
        values = tuple(_hit_value(hit) for hit in hits)
        if values in taken:
            renewed = _renew(ctx, hits, values, taken)
            if renewed is None:
                ctx.note("identity_value_not_unique", GENERATOR_LIMIT, constraint.name, constraint)
                continue
            values = renewed
        taken.add(values)


def _renew(
    ctx: _Context, hits: list[object], values: tuple[str, ...], taken: set[tuple[str, ...]]
) -> tuple[str, ...] | None:
    for index, hit in enumerate(hits):
        slot = _slot(hit)
        if slot is None:
            continue
        for value in itertools.islice(_alternatives(ctx, slot, values[index]), 500):
            candidate = values[:index] + (value,) + values[index + 1 :]
            if candidate not in taken:
                _write(slot, value)
                return candidate
    return None


def _alternatives(ctx: _Context, slot: tuple[etree._Element, str | None], current: str):
    """Other values the slot's type and facets accept, nearest-looking first."""
    spec = ctx.value_specs.get(slot)
    if spec is None:
        return  # a fixed or default value, which must stay as it is
    local, facets = spec
    if local == "ID":
        for _ in range(50):
            yield ctx.next_id()
        return
    checker = None
    if local in _BUILTIN_VALUES and local not in _UNCHECKED_TYPES:
        checker = _value_checker(local, _checkable(facets))
    notes_before = len(ctx.report)
    pool = _candidates(ctx, local, facets)
    del ctx.report[notes_before:]
    tried = {current}
    suffixed = (f"{current}{k}" for k in range(1, 100))
    for value in itertools.chain(pool, _numeric_steps(current), suffixed, _bumped(current)):
        if value in tried:
            continue
        tried.add(value)
        if checker is None or _accepts(checker, value):
            yield value


def _numeric_steps(current: str):
    try:
        number = Decimal(current.strip())
    except InvalidOperation:
        return
    if not number.is_finite():
        return
    for step in range(1, 50):
        yield format(number + step, "f")
        yield format(number - step, "f")


def _bumped(current: str):
    """``current`` with one letter or digit moved along its alphabet, last position first.

    Keeps a value inside character-class patterns such as ``[A-Z][0-9]{2}``.
    """
    for index in range(len(current) - 1, -1, -1):
        char = current[index]
        for alphabet in (
            "0123456789",
            "abcdefghijklmnopqrstuvwxyz",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        ):
            if char in alphabet:
                start = alphabet.index(char)
                for step in range(1, len(alphabet)):
                    yield current[:index] + alphabet[(start + step) % len(alphabet)] + current[index + 1 :]


def _resolve_keyref(
    ctx: _Context,
    root: etree._Element,
    scope: etree._Element,
    constraint: IdentityConstraint,
    scopes: list[tuple[etree._Element, ElementDecl]],
) -> None:
    """Point each keyref tuple at a tuple of the key it refers to, visible from ``scope``."""
    if constraint.kind != "keyref":
        return
    if constraint.refer_id is None:
        ctx.note("keyref_target_unknown", SCHEMA_INCOMPLETE, constraint.refer, constraint)
        return
    key_tuples: list[tuple[str, ...]] = []
    # A key's table is visible in its own scope and every ancestor scope.
    for node, declaration in scopes:
        if not _in_tree(node, root) or not (node is scope or any(a is scope for a in node.iterancestors())):
            continue
        for key in declaration.identity_constraints:
            if key.id != constraint.refer_id:
                continue
            for target in _select(ctx, key, node):
                hits = _fields(ctx, key, target)
                if hits is not None:
                    key_tuples.append(tuple(_hit_value(hit) for hit in hits))
    for target in _select(ctx, constraint, scope):
        if not _in_tree(target, root):
            continue
        hits = _fields(ctx, constraint, target)
        if hits is None:
            continue  # a keyref with an absent field constrains nothing
        if tuple(_hit_value(hit) for hit in hits) in key_tuples:
            continue
        if key_tuples and _point_at(ctx, hits, key_tuples):
            continue
        removable = _removable(ctx, target, root)
        if removable is not None:
            _drop(ctx, removable)
        else:
            ctx.note("keyref_without_key", GENERATOR_LIMIT, constraint.name, constraint)


def _point_at(ctx: _Context, hits: list[object], key_tuples: list[tuple[str, ...]]) -> bool:
    slots = [_slot(hit) for hit in hits]
    if any(slot is None or slot not in ctx.value_specs for slot in slots):
        return False
    for values in key_tuples:
        if len(values) == len(slots) and all(
            _fits(ctx, slot, v) for slot, v in zip(slots, values, strict=True)
        ):
            for slot, value in zip(slots, values, strict=True):
                _write(slot, value)
            return True
    return False


def _fits(ctx: _Context, slot: tuple[etree._Element, str | None], value: str) -> bool:
    local, facets = ctx.value_specs[slot]
    if local not in _BUILTIN_VALUES or local in _UNCHECKED_TYPES:
        return True
    checker = _value_checker(local, _checkable(facets))
    return checker is None or _accepts(checker, value)


def _recorded(  # noqa: ANN001 - produce is any value function of this module
    ctx: _Context, node: etree._Element, attribute: str | None, produce, *args
) -> str:
    """Call ``produce(*args)`` and remember which type and facets its value came from."""
    ctx.last_spec = None
    value = produce(*args)
    if ctx.last_spec is not None:
        ctx.value_specs[(node, attribute)] = ctx.last_spec
    return value


# ---------------------------------------------------------------------------
# Simple values
# ---------------------------------------------------------------------------


def _value_for_type_name(
    ctx: _Context, type_name: str | None, extra_facets: list[Facet], owner: object | None = None
) -> str:
    if type_name is None:
        return _builtin_value(ctx, "string", extra_facets)
    resolved = _resolve_type(ctx, type_name, owner)
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
            ctx, target.simple_content_base, extra_facets + target.simple_content_facets, target
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
    own = list(simple.facets)
    extra = list(extra_facets or [])
    if any(f.kind == "enumeration" for f in extra):
        # A derived enumeration replaces the base's set rather than adding to it
        # (SIRI: DaysOfWeekEnumerationx narrows DayTypeEnumeration).
        own = [f for f in own if f.kind != "enumeration"]
    facets = own + extra
    if simple.derivation == "list":
        if simple.item_inline is not None:
            item = _simple_value(ctx, simple.item_inline, stack)
        else:
            item = _value_for_type_name(ctx, simple.item_type, [], simple)
        # On a list the length facets count items, not characters (GML
        # CategoryExtent restricts a name list to exactly two).
        length = _int_facet(facets, "length")
        count = length if length is not None else max(1, _int_facet(facets, "minLength") or 0)
        return " ".join([item] * count)
    if simple.derivation == "union":
        enumeration = next((f.value for f in facets if f.kind == "enumeration"), None)
        if enumeration is not None:
            # Values enumerated on a restricted union are members by definition;
            # a sample from its first member type need not be one (SIRI DayType).
            return enumeration
        if simple.member_types:
            return _value_for_type_name(ctx, simple.member_types[0], facets, simple)
        if simple.member_inline:
            return _simple_value(ctx, simple.member_inline[0], stack, facets)
        ctx.note("union_without_members", SCHEMA_INCOMPLETE, simple.name, simple)
        return "text"
    # restriction / atomic: walk to the base, accumulating facets.
    if simple.base:
        resolved = _resolve_type(ctx, simple.base, simple)
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
    """A value of built-in type ``local`` that satisfies ``facets``.

    Candidates come from the enumeration, the type's placeholder and lexical
    variants, the range bounds and the pattern sampler. Each one is checked
    against a throw-away schema carrying the same facets, so a value only goes
    out once libxml2 accepts it. When nothing passes -- or the facets cannot
    be checked -- the first candidate is used.
    """
    ctx.last_spec = (local, facets)
    has_enumeration = any(f.kind == "enumeration" for f in facets)
    if local == "ID" and not has_enumeration:
        return ctx.next_id()
    known = local in _BUILTIN_VALUES
    if not known:
        # Not a built-in we know: the value below is a guess.
        ctx.note("builtin_unknown", GENERATOR_LIMIT, local)
    notes_before = len(ctx.report)
    candidates = _candidates(ctx, local, facets) or ["string"]
    checker = None
    if known and facets and local not in _UNCHECKED_TYPES:
        checker = _value_checker(local, _checkable(facets))
    if checker is None:
        return candidates[0]
    for candidate in candidates:
        if _accepts(checker, candidate):
            # The value is valid after all, so nothing noted on the way applies.
            del ctx.report[notes_before:]
            return candidate
    if len(ctx.report) == notes_before:
        ctx.note("value_unsatisfiable", GENERATOR_LIMIT, local)
    return candidates[0]


def _candidates(ctx: _Context, local: str, facets: list[Facet]) -> list[str]:
    enumeration = _enumeration_value(local, facets)
    if enumeration is not None:
        # Nothing outside the enumeration can be valid.
        return _unique([enumeration, *(f.value for f in facets if f.kind == "enumeration")])
    string_like = local in _STRING_TYPES or local not in _BUILTIN_VALUES
    if local in _INTEGER_TYPES or local in _DECIMAL_TYPES:
        values = _numeric_candidates(local, facets)
    elif string_like:
        values = _string_candidates(local, facets)
    else:
        bounds = [f.value for f in reversed(facets) if f.kind in ("minInclusive", "maxInclusive")]
        values = [
            _BUILTIN_VALUES[local],
            *_VARIANTS.get(local, ()),
            *bounds,
            *_binary_candidates(local, facets),
        ]
    patterns = _pattern_candidates(ctx, facets)
    # A string placeholder rarely matches a pattern; a number or a date often does.
    return _unique(patterns + values if string_like else values + patterns)


def _pattern_candidates(ctx: _Context, facets: list[Facet]) -> list[str]:
    min_length = _int_facet(facets, "length") or _int_facet(facets, "minLength") or 0
    values: list[str] = []
    unsupported: str | None = None
    # Facets run from the base type to the most derived one; the latter is the
    # tightest, so its pattern goes first.
    for pattern in [f.value for f in reversed(facets) if f.kind == "pattern"]:
        shortest = sample_from_pattern(pattern)
        if shortest is None:
            unsupported = unsupported or pattern
            continue
        values.append(shortest)
        if len(shortest) < min_length:
            for stretch in (min_length, 1):
                longer = sample_from_pattern(pattern, stretch=stretch)
                if longer is not None:
                    values.append(longer)
    if unsupported is not None and not values:
        # We could not read the pattern, so the placeholder will almost
        # certainly violate it — a prime source of invalid samples.
        ctx.note("pattern_unsupported", GENERATOR_LIMIT, unsupported)
    return values


def _binary_candidates(local: str, facets: list[Facet]) -> list[str]:
    """Zero octets at the lengths the facets ask for -- binary lengths count octets (UCI SHA_2_Hash)."""
    if local not in ("hexBinary", "base64Binary"):
        return []
    values = []
    for kind in ("length", "minLength", "maxLength"):
        size = _int_facet(facets, kind)
        if size is None or size > 65_536:
            continue
        octets = bytes(size)
        values.append(octets.hex() if local == "hexBinary" else base64.b64encode(octets).decode("ascii"))
    return values


def _string_candidates(local: str, facets: list[Facet]) -> list[str]:
    base = _BUILTIN_VALUES.get(local, "string")
    length = _int_facet(facets, "length")
    if length is not None:
        return [_sized(base, length)]
    size = len(base)
    min_length = _int_facet(facets, "minLength")
    max_length = _int_facet(facets, "maxLength")
    if min_length is not None:
        size = max(size, min_length)
    if max_length is not None:
        size = min(size, max_length)
    return [_sized(base, size), base]


def _sized(base: str, size: int) -> str:
    return (base * (size // max(len(base), 1) + 1))[:size] if size > 0 else ""


# A lower bound up to this size reads naturally as the sample (an age of 0);
# beyond it the type's own placeholder is nicer, when it is in range.
_SMALL_BOUND = Decimal(1_000_000)


def _numeric_candidates(local: str, facets: list[Facet]) -> list[str]:
    """In-range numbers, computed in Decimal: floats turned ±99999999999999999999.99 into ±1E20."""
    integer = local in _INTEGER_TYPES
    fraction = _int_facet(facets, "fractionDigits")
    places = 0 if integer else (fraction if fraction is not None else 1)
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as context:
        context.prec = 1000  # double bounds reach 1.8E308
        lo = _bound(facets, "minInclusive", "minExclusive", quantum, ROUND_CEILING)
        hi = _bound(facets, "maxInclusive", "maxExclusive", -quantum, ROUND_FLOOR)
        options: list[Decimal] = []
        if lo is not None and abs(lo) <= _SMALL_BOUND:
            options.append(lo)
        options += [Decimal(_BUILTIN_VALUES.get(local, "1")), Decimal(1), Decimal(0)]
        options += [value for value in (lo, hi) if value is not None]
        if lo is not None and hi is not None:
            options.append(((lo + hi) / 2).quantize(quantum, rounding=ROUND_FLOOR))
        inside = [v for v in options if (lo is None or v >= lo) and (hi is None or v <= hi)]
        return _unique(format(v.quantize(quantum), "f") for v in (inside or options))


def _bound(
    facets: list[Facet], inclusive: str, exclusive: str, nudge: Decimal, rounding: str
) -> Decimal | None:
    """The most derived bound of one side, rounded onto the value grid."""
    for facet in reversed(facets):
        if facet.kind not in (inclusive, exclusive):
            continue
        try:
            value = Decimal(facet.value.strip())
        except InvalidOperation:
            continue
        if not value.is_finite():
            continue
        rounded = value.quantize(abs(nudge), rounding=rounding)
        if facet.kind == exclusive and rounded == value:
            rounded += nudge
        return rounded
    return None


def _int_facet(facets: list[Facet], kind: str) -> int | None:
    for facet in reversed(facets):
        if facet.kind == kind and facet.value.strip().isdigit():
            return int(facet.value)
    return None


def _unique(values) -> list[str]:  # noqa: ANN001 - any iterable of str
    return list(dict.fromkeys(values))


# Lexical variants tried after the placeholder, e.g. when a pattern insists on
# a time zone (UCI: ``.+Z``).
_VARIANTS: dict[str, tuple[str, ...]] = {
    "dateTime": (
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:00.000Z",
        "2026-01-01T00:00:00.000",
    ),
    "date": ("2026-01-01Z", "2026-01-01+00:00"),
    "time": ("00:00:00Z", "00:00:00+00:00", "00:00:00.000"),
    "gYear": ("2026Z",),
    "gYearMonth": ("2026-01Z",),
    "gMonth": ("--01Z",),
    "gMonthDay": ("--01-01Z",),
    "gDay": ("---01Z",),
    "duration": ("PT1H", "P1Y", "PT0S"),
    "boolean": ("false", "1", "0"),
    "language": ("en-US", "de"),
    "hexBinary": ("0000",),
    "base64Binary": ("AAAA",),
}

# Facets a one-off XSD 1.0 restriction can carry. Anything else (XSD 1.1
# assertions, explicitTimezone) is left out of the check.
_CHECKABLE_FACETS = {
    "length",
    "minLength",
    "maxLength",
    "pattern",
    "enumeration",
    "whiteSpace",
    "maxInclusive",
    "maxExclusive",
    "minInclusive",
    "minExclusive",
    "totalDigits",
    "fractionDigits",
}
# Types whose values a stand-alone element cannot check: identity and entity
# references need the rest of the document, QNames a namespace context, and
# libxml2 does not know the XSD 1.1 additions.
_UNCHECKED_TYPES = {
    "ID",
    "IDREF",
    "IDREFS",
    "ENTITY",
    "ENTITIES",
    "QName",
    "NOTATION",
    "anyType",
    "anySimpleType",
    "anyAtomicType",
    "dateTimeStamp",
    "dayTimeDuration",
    "yearMonthDuration",
}


def _checkable(facets: list[Facet]) -> tuple[tuple[str, str], ...]:
    """Hashable facet list for the checker: repeatable facets all, the others most derived."""
    single: dict[str, str] = {}
    repeatable: list[tuple[str, str]] = []
    for facet in facets:
        if facet.kind not in _CHECKABLE_FACETS:
            continue
        if facet.kind in ("pattern", "enumeration"):
            repeatable.append((facet.kind, facet.value))
        else:
            single[facet.kind] = facet.value
    return tuple(repeatable) + tuple(single.items())


@lru_cache(maxsize=4096)
def _value_checker(local: str, facets: tuple[tuple[str, str], ...]) -> etree.XMLSchema | None:
    """A one-element schema accepting exactly the values of ``local`` under ``facets``."""
    body = "".join(f"<xs:{kind} value={quoteattr(value)}/>" for kind, value in facets)
    xsd = (
        f'<xs:schema xmlns:xs="{XSD_NS}"><xs:element name="v"><xs:simpleType>'
        f'<xs:restriction base="xs:{local}">{body}</xs:restriction>'
        "</xs:simpleType></xs:element></xs:schema>"
    )
    try:
        return etree.XMLSchema(etree.fromstring(xsd))
    except (etree.XMLSchemaParseError, etree.XMLSyntaxError):
        # Contradictory facets (minInclusive next to minExclusive) and the like.
        return None


def _accepts(checker: etree.XMLSchema, value: str) -> bool:
    element = etree.Element("v")
    try:
        element.text = value
    except ValueError:  # a control character no XML document can carry
        return False
    return bool(checker.validate(element))
