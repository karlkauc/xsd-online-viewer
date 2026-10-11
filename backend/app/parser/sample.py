"""Generate a skeleton XML instance for an element of a parsed schema.

The generator walks the content model the way XMLSpy's "Generate Sample XML"
does: required particles once, the first branch of a choice, the first
enumeration value, type-appropriate values for built-in types, and a
best-effort string for ``xs:pattern`` facets. Optional content is included
on request, repeatable particles up to ``repeat`` times within maxOccurs.

Values are meant to look like data: the name of an element or attribute
suggests one (app.parser.sample_hints), and dates and numbers differ from
one occurrence to the next. Whatever is offered that way is checked against
the declared type and facets before it is used, so it cannot make a sample
invalid.

Identity constraints (xs:key, xs:keyref, xs:unique) and ID/IDREF are settled
on the finished tree, since they concern the whole document. XSD 1.1 type
alternatives are followed where their tests are simple attribute
comparisons; assertions are not evaluated. It never raises on an incomplete
schema: unresolved references become XML comments so the user can see what
could not be filled in.
"""

from __future__ import annotations

import base64
import datetime
import itertools
import re
import sys
from collections.abc import Callable
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
from app.parser.regex_sample import samples_from_pattern
from app.parser.sample_hints import hinted_values
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

# Reasons that mean the loaded files do not define a referenced declaration,
# so libxml2 cannot compile the schema. Deliberately narrow: the audit of
# URL-loaded schemas (2026-09-11) saw extension_base_not_found and
# restriction_base_not_found in schemas that compile and validate.
MISSING_REFERENCE_REASONS = frozenset({"type_not_found", "element_ref_not_found"})


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

    @property
    def missing_references(self) -> list[str]:
        """Declarations the schema references but never loaded, first-seen order.

        Such a schema cannot compile, so there is no point checking the sample.
        """
        names = (e.where for e in self.entries if e.reason in MISSING_REFERENCE_REASONS)
        return list(dict.fromkeys(name for name in names if name))

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
            element_form=attributes.get("elementFormDefault", "unqualified").strip(),
            attribute_form=attributes.get("attributeFormDefault", "unqualified").strip(),
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
    # ID values handed out so far: an ID must be unique in the document.
    used_ids: set[str] = field(default_factory=set)
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
    # Local name of the element or attribute whose value is being produced.
    value_name: str | None = None
    # How many values of each built-in type went out, so they need not all look alike.
    value_counts: dict[str, int] = field(default_factory=dict)
    # Optional attributes left out, in case a key turns out to need one, and
    # the optional ones that went in, which may be taken out again.
    skipped_attributes: dict[etree._Element, dict[str, AttributeDecl]] = field(default_factory=dict)
    optional_attributes: set[tuple[etree._Element, str]] = field(default_factory=set)
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
        while True:
            self.id_counter += 1
            value = f"id{self.id_counter}"
            if value not in self.used_ids:
                self.used_ids.add(value)
                return value

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
    # Every nesting level costs several Python frames, here and in the cost
    # estimate for choices; a deep but legitimate schema must not hit the
    # interpreter's default limit. Raised for good rather than per call: the
    # limit is process-wide, and restoring it would pull it out from under a
    # sample being generated on another thread.
    if sys.getrecursionlimit() < _RECURSION_LIMIT:
        sys.setrecursionlimit(_RECURSION_LIMIT)
    try:
        root = (
            _unresolved_root(ctx, element)
            if declaration is None
            else _generated_root(ctx, declaration)
        )
    except RecursionError:
        ctx = _build_context(model, options)
        root = _unfinished_root(ctx, declaration or element)
    _merge_repeated_comments(root)
    # Declare the prefixes we used (and only those) on the root.
    nsmap = dict(ctx.nsmap)
    default_namespace = _default_namespace(ctx, declaration, root)
    if default_namespace is not None:
        nsmap = {p: uri for p, uri in nsmap.items() if uri != default_namespace}
        nsmap[None] = default_namespace
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
    _resolve_idrefs(ctx, root)
    if ctx.budget_hit:
        root.append(
            etree.Comment(
                f" sample truncated: size limit of {ctx.options.max_elements} elements reached,"
                " further optional content omitted "
            )
        )
        ctx.note("size_limit", GENERATOR_LIMIT, element.name, element)
    return root


# Python frames the generator may use; see generate_sample_with_report.
_RECURSION_LIMIT = 6000


def _unfinished_root(ctx: _Context, element: ElementDecl) -> etree._Element:
    """What is left when the schema nests deeper than the generator can follow."""
    namespace = _element_namespace(ctx, element, is_root=True) if element.name else None
    if namespace:
        ctx.prefix_for(namespace)
    root = etree.Element(_tag(namespace, element.name))
    root.append(etree.Comment(" content nests too deeply to generate "))
    ctx.note("recursion_limit", GENERATOR_LIMIT, element.name, element)
    return root


def _merge_repeated_comments(root: etree._Element) -> None:
    """Keep one of several identical comments in a row (a note per repetition says nothing new)."""
    previous: etree._Element | None = None
    for node in list(root.iter()):
        if not isinstance(node, etree._Comment):
            previous = None
            continue
        if (
            previous is not None
            and previous.getnext() is node
            and previous.text == node.text
            and node.getparent() is not None
        ):
            node.getparent().remove(node)
            continue
        previous = node


def _default_namespace(
    ctx: _Context, declaration: ElementDecl | None, root: etree._Element
) -> str | None:
    """The root's namespace, when the document can use it unprefixed.

    A schema that binds its target namespace as the default namespace is
    written without prefixes, and so are its instance documents. That only
    works when every element is in that one namespace -- an unqualified local
    element would need ``xmlns=""`` -- and when nothing else needs the prefix:
    an attribute or a QName value never uses the default namespace.
    """
    namespace = etree.QName(root).namespace
    settings = ctx.settings_of(declaration)
    if namespace is None or settings is None or settings.default_namespace != namespace:
        return None
    prefixes = {prefix for prefix, uri in ctx.nsmap.items() if uri == namespace}
    if prefixes & ctx.value_prefixes:
        return None
    for node in root.iter(etree.Element):
        if etree.QName(node).namespace != namespace:
            return None
        if any(etree.QName(name).namespace == namespace for name in node.attrib):
            return None
    return namespace


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
    if element.alternatives:
        _fill_by_alternative(ctx, node, element, depth=depth, type_stack=type_stack)
        return
    typed = _typed_declaration(ctx, element)
    literal = element.fixed if element.fixed is not None else element.default
    if literal is not None and _has_complex_type(ctx, typed):
        # The value constraint only replaces the text: a simpleContent type
        # still brings its attributes (a fixed currency amount with a unit).
        _fill_typed(ctx, node, typed, depth=depth, type_stack=type_stack)
        if len(node) == 0:
            node.text = literal
            ctx.value_specs.pop((node, None), None)
        return
    if element.fixed is not None:
        node.text = element.fixed
        return
    if typed is not element:
        _fill_typed(
            ctx,
            node,
            typed.model_copy(update={"default": element.default}),
            depth=depth,
            type_stack=type_stack,
        )
        return
    _fill_typed(ctx, node, element, depth=depth, type_stack=type_stack)


_NUMERIC_VALUE_COMPARISON = re.compile(r"@[\w.:-]+\s+(?:lt|le|gt|ge|eq|ne)\s+-?\d+(?:\.\d+)?(?![\w.])")
_VALUE_COMPARISON = re.compile(r"\s(lt|le|gt|ge|eq|ne)\s")
_SEQUENCE_COMPARISON = re.compile(r"(@[\w.:-]+)\s*=\s*\(([^()]*)\)")


def _as_xpath_1(test: str) -> str:
    """The XPath 2.0 a type alternative usually tests with, in XPath 1.0 terms.

    Attributes are untyped while an alternative is chosen. A general
    comparison (``@n < 300``) casts them to the other operand's type, as
    XPath 1.0 does. A value comparison (``@n lt 300``) casts them to a string
    instead, which makes comparing with a number a type error -- and an
    alternative whose test fails that way is simply not chosen.
    """
    test = _NUMERIC_VALUE_COMPARISON.sub("false()", test)

    def operator(match: re.Match[str]) -> str:
        if match.group(1) not in ("eq", "ne"):
            raise etree.XPathError("string ordering is not XPath 1.0")
        return " = " if match.group(1) == "eq" else " != "

    test = _VALUE_COMPARISON.sub(operator, test)
    return _SEQUENCE_COMPARISON.sub(
        lambda m: "(" + " or ".join(f"{m.group(1)}={item.strip()}" for item in m.group(2).split(",")) + ")",
        test,
    )


def _fill_by_alternative(
    ctx: _Context,
    node: etree._Element,
    element: ElementDecl,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    """Fill an element whose type depends on its attributes (XSD 1.1 xs:alternative).

    Which alternative applies is only known once the attributes are there,
    and those come from the type. So: fill with one type, see which
    alternative its attributes select, and go on with that one until the type
    used and the type selected agree.
    """
    plain = element.model_copy(update={"alternatives": []})
    try:
        tests = [
            None
            if alternative.test is None
            else etree.XPath(
                f"boolean({_as_xpath_1(alternative.test)})",
                namespaces={p: uri for p, uri in ctx.model.namespaces.items() if p},
            )
            for alternative in element.alternatives
        ]
    except etree.XPathError:
        tests = None
    untested = next((i for i, a in enumerate(element.alternatives) if a.test is None), None)
    notes_before, cuts_before = len(ctx.report), ctx.cuts
    # Start from the declared type; without one, from the default alternative.
    choice = None if not _is_empty_decl(element) or untested is None else untested
    tried: list[int | None] = []
    while True:
        tried.append(choice)
        declaration = plain
        if choice is not None:
            alternative = element.alternatives[choice]
            declaration = plain.model_copy(
                update={
                    "type_name": alternative.type_name,
                    "type_inline_simple": alternative.type_inline_simple,
                    "type_inline_complex": alternative.type_inline_complex,
                }
            )
        _fill_element(ctx, node, declaration, depth=depth, type_stack=type_stack)
        if tests is None:
            break
        try:
            selected = next(
                (i for i, test in enumerate(tests) if test is None or test(node)), None
            )
        except etree.XPathError:
            tests = None
            break
        if selected == choice or _same_type(element, selected, choice):
            return
        if selected in tried:
            tests = None
            break
        # Start over with the type the attributes ask for.
        for child in list(node):
            node.remove(child)
        node.attrib.clear()
        node.text = None
        del ctx.report[notes_before:]
        ctx.cuts = cuts_before
        choice = selected
    # The tests are beyond XPath 1.0, or no type selects itself.
    ctx.note("type_alternative_unsettled", GENERATOR_LIMIT, element.name, element)


def _same_type(element: ElementDecl, first: int | None, second: int | None) -> bool:
    """Whether two alternatives (None: the declared type) name the same type."""

    def name(index: int | None) -> str | None:
        return element.type_name if index is None else element.alternatives[index].type_name

    return name(first) is not None and name(first) == name(second)


def _typed_declaration(ctx: _Context, element: ElementDecl) -> ElementDecl:
    """The declaration whose type ``element`` has.

    An element without a type of its own takes the type of its substitution
    group head; left empty it fails wherever the head's type requires content.
    """
    current, seen = element, {element.id}
    while _is_empty_decl(current) and current.substitution_group:
        head = ctx.lookup(ctx.global_element_by_key, current.substitution_group, current)
        if head is None or head.id in seen:
            break
        seen.add(head.id)
        current = head
    return current if not _is_empty_decl(current) else element


def _has_complex_type(ctx: _Context, element: ElementDecl) -> bool:
    if element.type_inline_complex is not None:
        return True
    if element.type_inline_simple is not None or element.type_name is None:
        return False
    resolved = _resolve_type(ctx, element.type_name, element, quiet=True)
    return resolved is not None and resolved[0] == "complex"


def _fill_typed(
    ctx: _Context,
    node: etree._Element,
    element: ElementDecl,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    """Content for ``node`` from the type ``element`` declares."""
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
            if (
                base is None
                and not current.simple_content_base
                and not quiet
                and ctx.split_qname(current.base, current)[0] != XSD_NS
            ):
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
        owner = next(
            (m for m in chain if m.simple_content_base or m.simple_content_inline is not None), None
        )
        facets = [f for m in reversed(chain) for f in _by_step(m.simple_content_facets)]
        node.text = _recorded(ctx, node, None, _simple_content_value, ctx, owner, facets, ())
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
    if decl.target_namespace and not decl.is_global:
        return decl.target_namespace  # XSD 1.1 targetNamespace on a local attribute
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
        tag = _tag(namespace, decl.name)
        # An empty string is a value too (fixed=""), so no ``or`` chain here.
        literals = (attribute.fixed, decl.fixed, attribute.default, decl.default)
        value = next((v for v in literals if v is not None), None)
        if attribute.use != "required" and not ctx.options.include_optional and value is None:
            ctx.skipped_attributes.setdefault(node, {})[tag] = decl
            continue
        if attribute.use != "required" and value is None:
            ctx.optional_attributes.add((node, tag))
        _set_attribute(ctx, node, tag, namespace, decl, value)
    for ref in group_refs:
        if ref in seen_groups:
            continue
        seen_groups.add(ref)
        group = ctx.lookup(ctx.attr_group_by_key, ref, owner)
        if group is not None:
            _fill_attributes(ctx, node, group.attributes, group.attribute_group_refs, seen_groups, group)


def _set_attribute(
    ctx: _Context,
    node: etree._Element,
    tag: str,
    namespace: str | None,
    decl: AttributeDecl,
    value: str | None = None,
) -> None:
    if value is None:
        if decl.type_inline is not None:
            value = _recorded(ctx, node, tag, _simple_value, ctx, decl.type_inline, ())
        else:
            value = _recorded(ctx, node, tag, _value_for_type_name, ctx, decl.type_name, [], decl)
    if namespace:
        ctx.prefix_for(namespace)
    node.set(tag, value)


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------


def _occurrences(ctx: _Context, particle: Particle) -> int:
    if particle.max_occurs == 0:
        # maxOccurs="0" takes the particle out of the content model (goAML).
        return 0
    required = particle.min_occurs
    room = ctx.options.max_elements - ctx.emitted
    if required > 1 and required > room:
        # minOccurs="400" inside minOccurs="400" is 160,000 elements; the
        # budget has to hold for required content as well.
        ctx.budget_hit = True
        return max(1, room)
    if not ctx.options.include_optional:
        return required
    if room <= 0:
        ctx.budget_hit = True
        return required
    # ``repeat`` shows a repeatable particle more than once, but never more
    # often than maxOccurs allows (FundsXML: MexID, maxOccurs="2").
    wanted = max(1, ctx.options.repeat)
    if particle.max_occurs != "unbounded":
        wanted = min(wanted, particle.max_occurs)
    return max(required, wanted)


def _emit_particle(
    ctx: _Context,
    parent: etree._Element,
    particle: Particle,
    *,
    depth: int,
    type_stack: tuple[str, ...],
) -> None:
    count = _occurrences(ctx, particle)
    if count < particle.min_occurs:
        parent.append(
            etree.Comment(
                f" {particle.min_occurs} occurrences of {_particle_label(particle)} required,"
                f" {count} shown: size limit "
            )
        )
        ctx.note("required_occurrences_cut", GENERATOR_LIMIT, _particle_label(particle), particle.element)
        ctx.cuts += 1
    cuts_before = ctx.cuts
    for turn in range(count):
        if turn < particle.min_occurs:
            _emit_occurrence(ctx, parent, particle, depth=depth, type_stack=type_stack, turn=turn)
        elif ctx.cuts != cuts_before or not _emit_tentatively(
            # Only here because optional content was asked for.
            ctx, parent, particle, _emit_occurrence, particle, depth, type_stack, turn
        ):
            # What could not be completed once will not be the next time either.
            break


def _emit_occurrence(
    ctx: _Context,
    parent: etree._Element,
    particle: Particle,
    *,
    depth: int,
    type_stack: tuple[str, ...],
    turn: int = 0,
) -> None:
    """One occurrence of ``particle``; ``turn`` counts its repetitions from 0."""
    if particle.kind == "element" and particle.element is not None:
        _emit_element_particle(
            ctx,
            parent,
            particle.element,
            depth=depth,
            type_stack=type_stack,
            optional=turn >= particle.min_occurs,
        )
    elif particle.kind in ("sequence", "all"):
        for child_particle in particle.children:
            _emit_particle(ctx, parent, child_particle, depth=depth, type_stack=type_stack)
    elif particle.kind == "choice":
        _emit_choice(ctx, parent, particle, depth=depth, type_stack=type_stack, turn=turn)
    elif particle.kind == "group-ref":
        group = particle.group_inline
        if group is None and particle.group_ref:
            group = ctx.lookup(ctx.group_by_key, particle.group_ref)
        if group is None or group.particle is None:
            parent.append(etree.Comment(f" group {particle.group_ref} not found in schema "))
            ctx.note("group_not_found", SCHEMA_INCOMPLETE, particle.group_ref)
            return
        ctx.file_stack.append(ctx.file_of(group))
        try:
            _emit_particle(ctx, parent, group.particle, depth=depth, type_stack=type_stack)
        finally:
            ctx.file_stack.pop()
    elif particle.kind == "any":
        if particle.min_occurs > 0:
            _emit_wildcard(ctx, parent, particle, depth=depth, type_stack=type_stack)
            return
        parent.append(etree.Comment(" any element allowed here "))
        ctx.note("wildcard_skipped", GENERATOR_LIMIT, "xs:any")


def _emit_choice(
    ctx: _Context,
    parent: etree._Element,
    particle: Particle,
    *,
    depth: int,
    type_stack: tuple[str, ...],
    turn: int = 0,
) -> None:
    picked = _pick_choice(ctx, particle.children, type_stack, turn)
    if picked is None:
        return
    chosen, endless = picked
    if chosen.min_occurs == 0 and endless:
        # The branch may stay empty, and filling it could only re-enter an
        # element that is already open (JATS def-list > def-list): that nests
        # down to the depth limit only to be cut there. An empty choice is valid.
        return
    if chosen.kind != "element":
        # No branch was a plain element, so we took a group or a
        # wildcard — the weakest guess this generator makes.
        ctx.note("choice_branch_not_element", GENERATOR_LIMIT, chosen.kind)
    if chosen.min_occurs > 0:
        _emit_particle(ctx, parent, chosen, depth=depth, type_stack=type_stack)
        return
    # The branch may be empty; show it once anyway, but take it back when its
    # content cannot be generated.
    forced = chosen.model_copy(update={"min_occurs": 1})
    _emit_tentatively(ctx, parent, chosen, _emit_particle, forced, depth, type_stack)


def _emit_tentatively(
    ctx: _Context,
    parent: etree._Element,
    optional: Particle,
    emit: Callable[..., None],
    particle: Particle,
    depth: int,
    type_stack: tuple[str, ...],
    turn: int | None = None,
) -> bool:
    """``emit(particle)`` for content the schema does not require, taken back if it breaks.

    Somewhere below, a required element may hit the recursion or depth guard,
    or have an abstract type nothing derives from, and stay empty; that would
    make the document invalid. ``optional`` is not required, so leave it out
    instead — whether it is an element or a whole group (INSPIRE: an optional
    sequence around gml:TopoComplex). Returns whether the content stayed.
    """
    kept = len(parent)
    cuts_before = ctx.cuts
    notes_before = len(ctx.report)
    if turn is None:
        emit(ctx, parent, particle, depth=depth, type_stack=type_stack)
    else:
        emit(ctx, parent, particle, depth=depth, type_stack=type_stack, turn=turn)
    if ctx.cuts == cuts_before:
        return True
    for node in parent[kept:]:
        parent.remove(node)
    name = _particle_label(optional)
    parent.append(etree.Comment(f" optional {name} omitted: its content cannot be generated "))
    ctx.cuts = cuts_before
    # The subtree is gone, so its degradations no longer describe the output;
    # the one fact that survives is that we dropped it.
    del ctx.report[notes_before:]
    ctx.note("optional_subtree_dropped", GENERATOR_LIMIT, name, optional.element)
    return False


def _particle_label(particle: Particle) -> str:
    if particle.element is not None:
        return particle.element.name or particle.element.ref or "element"
    return particle.group_ref or particle.kind


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
    # An optional occurrence whose content cannot be completed is taken back
    # by _emit_tentatively, one level up.
    ctx.open_elements.append(declaration.id)
    try:
        _fill_element(ctx, child, declaration, depth=depth, type_stack=type_stack)
    finally:
        ctx.open_elements.pop()


def _pick_choice(
    ctx: _Context, children: list[Particle], type_stack: tuple[str, ...] = (), turn: int = 0
) -> tuple[Particle, bool] | None:
    """A branch that can end, preferring a plain element, then document order.

    A choice that repeats shows a different branch each ``turn``, among the
    plain elements that can end, so the sample does not hide the alternatives.

    A branch that can only be completed by nesting an element or type we are
    already inside never terminates (JATS: alternatives > array > alternatives),
    so it is taken only when every branch is like that. The flag says whether
    the chosen one is such a branch.
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
    best = ranked[0]
    if turn:
        peers = [
            i
            for i in ranked
            if not endless[i] and (usable[i].kind == "element") == (usable[best].kind == "element")
        ]
        if peers:
            best = peers[turn % len(peers)]
    return usable[best], endless[best]


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
    target = _wildcard_target(ctx)
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
    excluded = {
        target if t == "##targetNamespace" else None if t == "##local" else t
        for t in (particle.wildcard_not_namespace or "").split()
    }
    members = [
        m
        for m in _wildcard_members(ctx, constraint, target)
        if not particle.wildcard_not_namespace
        or (m.target_namespace or ctx.namespace_of(m)) not in excluded
    ]
    member = next((m for m in members if m.id not in ctx.open_elements), None)
    if member is None:
        parent.append(etree.Comment(" any element allowed here "))
        # The wildcard is required, so the element around it is incomplete;
        # when that one is optional it is left out (CFDI ComplementoConcepto).
        ctx.cuts += 1
        if members:
            # Only the elements we are inside match; nesting one would recurse.
            ctx.note("wildcard_skipped", GENERATOR_LIMIT, "xs:any")
        else:
            ctx.note("wildcard_without_declaration", SCHEMA_INCOMPLETE, constraint or "##any")
        return
    _emit_element_particle(ctx, parent, member, depth=depth, type_stack=type_stack)


def _wildcard_target(ctx: _Context) -> str | None:
    """The target namespace ``##other`` and ``##targetNamespace`` refer to: the declaring file's."""
    if ctx.file_stack and ctx.file_stack[-1] is not None:
        return ctx.declared_namespace(ctx.file_stack[-1])
    return ctx.model.target_namespace


def _wildcard_members(
    ctx: _Context, constraint: str | None, target: str | None
) -> list[ElementDecl]:
    """Concrete global elements a strict wildcard accepts, in document order."""
    key = f"{constraint or '##any'} {target}"
    if key not in ctx.wildcard_members:
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
            for head_name in candidate.substitution_groups if candidate.name else ():
                key = ctx.split_qname(head_name, candidate)
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


def _drop(
    ctx: _Context, node: etree._Element, why: str = "it would break an identity constraint"
) -> None:
    parent = node.getparent()
    name = etree.QName(node).localname
    parent.insert(parent.index(node), etree.Comment(f" optional {name} omitted: {why} "))
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
        if removable is not None:
            _drop(ctx, removable)
        elif not _supply_key_fields(ctx, constraint, target):
            ctx.note("key_field_missing", GENERATOR_LIMIT, constraint.name, constraint)


_ATTRIBUTE_FIELD = re.compile(r"^@(?:[\w.-]+:)?([\w.-]+)$")


def _supply_key_fields(ctx: _Context, constraint: IdentityConstraint, target: etree._Element) -> bool:
    """Add the optional attributes a key reads from ``target``, which must stay.

    Required-only output leaves optional attributes out, but a key makes its
    fields mandatory on every node it selects.
    """
    skipped = ctx.skipped_attributes.get(target, {})
    for expression in constraint.fields:
        if len(_run_xpath(ctx, constraint, expression, target)) == 1:
            continue
        match = _ATTRIBUTE_FIELD.match(expression.strip())
        tag = next(
            (t for t in skipped if match and etree.QName(t).localname == match.group(1)), None
        )
        if tag is None:
            return False
        _set_attribute(ctx, target, tag, etree.QName(tag).namespace, skipped.pop(tag))
    return _fields(ctx, constraint, target) is not None


def _make_distinct(
    ctx: _Context, root: etree._Element, scope: etree._Element, constraint: IdentityConstraint, _scopes: list
) -> None:
    if constraint.kind not in ("key", "unique"):
        return
    taken: set[tuple[str, ...]] = set()
    for target in _select(ctx, constraint, scope):
        if not _in_tree(target, root):
            continue
        hits = _fields(ctx, constraint, target)
        if hits is None:
            continue  # a unique may leave fields out; keys were settled in the pass before
        # Identity is decided in the value space: "1" and "true" are one boolean.
        types = [_slot_type(ctx, hit) for hit in hits]
        values = tuple(_canonical(t, _hit_value(hit)) for t, hit in zip(types, hits, strict=True))
        if values in taken:
            renewed = _renew(ctx, hits, types, values, taken)
            if renewed is None:
                # The type has no value left (an enumeration of two, used three
                # times): an occurrence the schema does not require can go.
                removable = _removable(ctx, target, root)
                if removable is not None:
                    _drop(ctx, removable)
                else:
                    ctx.note("identity_value_not_unique", GENERATOR_LIMIT, constraint.name, constraint)
                continue
            values = renewed
        taken.add(values)


def _slot_type(ctx: _Context, hit: object) -> str | None:
    slot = _slot(hit)
    spec = ctx.value_specs.get(slot) if slot is not None else None
    return spec[0] if spec is not None else None


_ZERO_OFFSET = re.compile(r"[+-]00:00$")


def _canonical(local: str | None, value: str) -> str:
    """One spelling per value, for the types whose lexical variants this generator emits."""
    text = value.strip()
    if local == "boolean":
        return {"1": "true", "0": "false"}.get(text, text)
    if local in _INTEGER_TYPES or local in _DECIMAL_TYPES:
        try:
            number = Decimal(text)
        except InvalidOperation:
            return text
        return format(number.normalize(), "f") if number.is_finite() else text
    if local in _TEMPORAL_TYPES:
        return _ZERO_OFFSET.sub("Z", text)
    return value


def _renew(
    ctx: _Context,
    hits: list[object],
    types: list[str | None],
    values: tuple[str, ...],
    taken: set[tuple[str, ...]],
) -> tuple[str, ...] | None:
    for index, hit in enumerate(hits):
        slot = _slot(hit)
        if slot is None:
            continue
        for value in itertools.islice(_alternatives(ctx, slot, _hit_value(hit)), 500):
            candidate = values[:index] + (_canonical(types[index], value),) + values[index + 1 :]
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
        seen = {current}
        for _ in range(50):
            notes_before = len(ctx.report)
            value = _id_value(ctx, facets)
            if value in seen:
                # The type's values are used up; say so once, at the caller.
                del ctx.report[notes_before:]
                return
            seen.add(value)
            yield value
        return
    checker = None
    if local in _BUILTIN_VALUES and local not in _UNCHECKED_TYPES:
        checker = _value_checker(local, _checkable(facets))
    notes_before = len(ctx.report)
    pool = _candidates(ctx, local, facets)
    del ctx.report[notes_before:]
    tried = {current}
    suffixed = (f"{current}{k}" for k in range(1, 100))
    steps = itertools.chain(_numeric_steps(current), _temporal_steps(local, current))
    for value in itertools.chain(pool, steps, suffixed, _bumped(current)):
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


def _temporal_steps(local: str, current: str):
    for step in range(1, 50):
        for signed in (step, -step):
            shifted = _shifted(local, current, signed, "day")
            if shifted is not None:
                yield shifted


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


def _resolve_idrefs(ctx: _Context, root: etree._Element) -> None:
    """Point every IDREF at an ID that is in the document.

    The placeholder ``id1`` only refers to something when the first ID
    generated is still there -- it may sit in a subtree that was dropped, or
    the document may have no ID at all. libxml2 does not check this; stricter
    validators do.
    """
    references = [
        (slot, spec[0])
        for slot, spec in ctx.value_specs.items()
        if spec[0] in ("IDREF", "IDREFS") and not any(f.kind == "enumeration" for f in spec[1])
    ]
    if not references:
        return
    ids: list[str] = []
    for slot, spec in ctx.value_specs.items():
        if spec[0] == "ID" and _in_tree(slot[0], root):
            value = _read(slot)
            if value:
                ids.append(value)
    for slot, local in references:
        node, attribute = slot
        current = _read(slot)
        if current is None or not _in_tree(node, root):
            continue
        tokens = current.split()
        if tokens and all(token in ids for token in tokens):
            continue
        if ids:
            count = max(1, len(tokens)) if local == "IDREFS" else 1
            _write(slot, " ".join(ids[i % len(ids)] for i in range(count)))
        elif attribute is not None and slot in ctx.optional_attributes:
            del node.attrib[attribute]
        elif attribute is None and node in ctx.optional_nodes:
            _drop(ctx, node, "the document has no ID it could refer to")
        else:
            # Only the reference itself is taken out: dropping the optional
            # ancestor of a required one would gut the sample (FundsXML
            # Positions, once the size limit cut the assets they refer to).
            ctx.note("idref_without_id", GENERATOR_LIMIT, etree.QName(node).localname)


def _read(slot: tuple[etree._Element, str | None]) -> str | None:
    element, attribute = slot
    return element.text if attribute is None else element.get(attribute)


def _recorded(  # noqa: ANN001 - produce is any value function of this module
    ctx: _Context, node: etree._Element, attribute: str | None, produce, *args
) -> str:
    """Call ``produce(*args)`` and remember which type and facets its value came from."""
    ctx.last_spec = None
    ctx.value_name = etree.QName(attribute or node.tag).localname
    value = produce(*args)
    if ctx.last_spec is not None:
        ctx.value_specs[(node, attribute)] = ctx.last_spec
    return value


# ---------------------------------------------------------------------------
# Simple values
# ---------------------------------------------------------------------------


def _value_for_type_name(
    ctx: _Context,
    type_name: str | None,
    extra_facets: list[Facet],
    owner: object | None = None,
    stack: tuple[str, ...] = (),
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
        return _simple_value(ctx, target, stack, extra_facets)
    if target.id in stack:
        # Not a legal schema, but the parser lets it through (two simpleContent
        # types extending each other).
        ctx.note("simple_recursion", GENERATOR_LIMIT, type_name, target)
        return "text"
    if target.simple_content_base or target.simple_content_inline is not None:
        facets = _by_step(target.simple_content_facets) + extra_facets
        return _simple_content_value(ctx, target, facets, stack)
    ctx.note("complex_type_as_text", GENERATOR_LIMIT, type_name)
    return _builtin_value(ctx, "string", extra_facets)


def _simple_content_value(
    ctx: _Context, owner: ComplexType | None, facets: list[Facet], stack: tuple[str, ...]
) -> str:
    """The text of a simpleContent type: its base's value under ``facets``."""
    if owner is None:
        return _builtin_value(ctx, "string", facets)
    stack = stack + (owner.id,)
    if owner.simple_content_inline is not None:
        # <xs:restriction base="…"><xs:simpleType>…: the anonymous type takes
        # the place of the base's content type.
        return _simple_value(ctx, owner.simple_content_inline, stack, facets)
    return _value_for_type_name(ctx, owner.simple_content_base, facets, owner, stack)


def _by_step(facets: list[Facet]) -> list[Facet]:
    """The facets of one derivation step, with its patterns folded into one.

    Several patterns in one restriction are alternatives, while the patterns
    of different steps must all match. Once the facets of a whole chain sit in
    one list that difference is gone, so each step contributes at most one
    pattern facet and every pattern facet stands for a step.
    """
    patterns = [f.value for f in facets if f.kind == "pattern"]
    if len(patterns) < 2:
        return list(facets)
    merged = Facet(kind="pattern", value="|".join(patterns))
    folded: list[Facet] = []
    for facet in facets:
        if facet.kind != "pattern":
            folded.append(facet)
        elif merged is not None:
            folded.append(merged)
            merged = None
    return folded


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
    own = _by_step(simple.facets)
    extra = list(extra_facets or [])
    if any(f.kind == "enumeration" for f in extra):
        # A derived enumeration replaces the base's set rather than adding to it
        # (SIRI: DaysOfWeekEnumerationx narrows DayTypeEnumeration).
        own = [f for f in own if f.kind != "enumeration"]
    facets = own + extra
    if simple.derivation == "list":
        return _list_value(ctx, simple, stack, facets)
    if simple.derivation == "union":
        enumeration = next((f.value for f in facets if f.kind == "enumeration"), None)
        if enumeration is not None:
            # Values enumerated on a restricted union are members by definition;
            # a sample from its first member type need not be one (SIRI DayType).
            return enumeration
        return _union_value(ctx, simple, stack, facets)
    # restriction / atomic: walk to the base, accumulating facets.
    if simple.base:
        resolved = _resolve_type(ctx, simple.base, simple)
        if resolved is not None and resolved[0] == "builtin":
            return _builtin_value(ctx, resolved[1], facets)
        if resolved is not None and resolved[0] == "simple":
            return _simple_value(ctx, resolved[1], stack, facets)
        ctx.note("simple_base_not_found", SCHEMA_INCOMPLETE, simple.base, simple)
    elif simple.derivation == "restriction" and simple.member_inline:
        # <xs:restriction><xs:simpleType>…: the parser keeps the anonymous base there.
        return _simple_value(ctx, simple.member_inline[0], stack, facets)
    return _builtin_value(ctx, "string", facets)


def _list_value(
    ctx: _Context, simple: SimpleType, stack: tuple[str, ...], facets: list[Facet]
) -> str:
    # On a restricted list, enumeration and pattern describe the whole value.
    enumeration = next((f.value for f in facets if f.kind == "enumeration"), None)
    if enumeration is not None:
        return enumeration
    if simple.item_inline is not None:
        item = _simple_value(ctx, simple.item_inline, stack)
    else:
        item = _value_for_type_name(ctx, simple.item_type, [], simple, stack)
    value = " ".join([item] * _item_count(facets))
    for pattern in [f.value for f in reversed(facets) if f.kind == "pattern"]:
        return next(samples_from_pattern(pattern), value)
    return value


def _item_count(facets: list[Facet]) -> int:
    """On a list the length facets count items, not characters (GML
    CategoryExtent restricts a name list to exactly two)."""
    length = _int_facet(facets, "length")
    if length is not None:
        return length
    count = max(1, _int_facet(facets, "minLength") or 0)
    max_length = _int_facet(facets, "maxLength")
    return count if max_length is None else min(count, max_length)


def _union_value(
    ctx: _Context, simple: SimpleType, stack: tuple[str, ...], facets: list[Facet]
) -> str:
    """A value of the first member type that can satisfy ``facets``."""
    members: list[Callable[[], str]] = [
        lambda name=name: _value_for_type_name(ctx, name, facets, simple, stack)
        for name in simple.member_types
    ]
    members += [
        lambda inline=inline: _simple_value(ctx, inline, stack, facets)
        for inline in simple.member_inline
    ]
    if not members:
        ctx.note("union_without_members", SCHEMA_INCOMPLETE, simple.name, simple)
        return "text"
    notes_before = len(ctx.report)
    first_value = members[0]()
    if not facets or len(ctx.report) == notes_before:
        return first_value
    # The facets of a restricted union (a pattern, mostly) rule the first
    # member out; another one may do.
    first_spec, first_notes = ctx.last_spec, ctx.report[notes_before:]
    for member in members[1:8]:
        del ctx.report[notes_before:]
        value = member()
        if len(ctx.report) == notes_before:
            return value
    ctx.report[notes_before:] = first_notes
    ctx.last_spec = first_spec
    return first_value


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

    Ahead of those come the nicer-looking values: one suggested by the name of
    the element or attribute, or one that differs from the last value of this
    type. They are only used when the same check accepts them.
    """
    ctx.last_spec = (local, facets)
    if local == "ID":
        return _id_value(ctx, facets)
    known = local in _BUILTIN_VALUES
    if not known:
        # Not a built-in we know: the value below is a guess.
        ctx.note("builtin_unknown", GENERATOR_LIMIT, local)
    checkable = known and local not in _UNCHECKED_TYPES
    if checkable:
        preferred = _preferred(ctx, local, facets)
        checker = _value_checker(local, _checkable(facets)) if preferred else None
        if checker is not None:
            for candidate in preferred:
                if _accepts(checker, candidate):
                    return candidate
    notes_before = len(ctx.report)
    candidates = _candidates(ctx, local, facets) or ["string"]
    checker = None
    if checkable and facets:
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


# Unconstrained decimals in turn, so that a document full of amounts does not
# read 0.0 throughout.
_DECIMAL_CYCLE = ("0.0", "1.5", "2.75", "10.0", "25.5", "100.0", "0.25", "3.0", "42.0", "7.5")
_RANGE_FACETS = frozenset(("minInclusive", "minExclusive", "maxInclusive", "maxExclusive"))
_HINTED_TYPES = frozenset(("string", "normalizedString", "token", "anyURI"))


def _preferred(ctx: _Context, local: str, facets: list[Facet]) -> list[str]:
    """Values to try before the plain placeholder; see _builtin_value."""
    if any(f.kind == "enumeration" for f in facets):
        return []
    if local in _HINTED_TYPES:
        hints = hinted_values(ctx.value_name, local)
        if not hints:
            return []
        turn = _turn(ctx, f"hint:{ctx.value_name}")
        return [hints[(turn + i) % len(hints)] for i in range(len(hints))]
    turn = _turn(ctx, local)
    if turn == 0:
        return []
    if local in _TEMPORAL_TYPES:
        varied = _shifted(local, _BUILTIN_VALUES[local], turn % 365, "day")
        return [varied] if varied is not None else []
    if any(f.kind in _RANGE_FACETS for f in facets):
        # A bound says more about a good value than variety does (an age of 0).
        return []
    if local in _DECIMAL_TYPES:
        return [_DECIMAL_CYCLE[turn % len(_DECIMAL_CYCLE)]]
    if local in _INTEGER_TYPES:
        start = int(_BUILTIN_VALUES[local])
        return [str(start + turn % 9 if start > 0 else start - turn % 9)]
    return []


def _turn(ctx: _Context, key: str) -> int:
    """How many values were asked for under ``key`` before this one."""
    turn = ctx.value_counts.get(key, 0)
    ctx.value_counts[key] = turn + 1
    return turn


def _id_value(ctx: _Context, facets: list[Facet]) -> str:
    """An ID not used in this document yet, within ``facets`` when the type has any."""
    relevant = [f for f in facets if f.kind in _CHECKABLE_FACETS and f.kind != "whiteSpace"]
    if not relevant:
        return ctx.next_id()
    # NCName has ID's lexical space without its document-wide uniqueness rule.
    checker = _value_checker("NCName", _checkable(relevant))
    enumerated = [f.value for f in relevant if f.kind == "enumeration"]
    if enumerated:
        pool = enumerated
        more: itertools.chain[str] | tuple[()] = ()
    else:
        notes_before = len(ctx.report)
        pool = _unique(_pattern_candidates(ctx, relevant) + _string_candidates("ID", relevant))
        del ctx.report[notes_before:]
        numbered = (f"id{n}" for n in range(1, 200))
        more = itertools.chain(
            numbered, *(itertools.islice(itertools.chain(_bumped(v), _suffixed(v)), 300) for v in pool)
        )
    for value in itertools.chain(pool, more):
        if value in ctx.used_ids:
            continue
        if checker is None or _accepts(checker, value):
            ctx.used_ids.add(value)
            return value
    ctx.note("id_not_unique" if enumerated else "value_unsatisfiable", GENERATOR_LIMIT, "ID")
    return pool[0] if pool else ctx.next_id()


def _suffixed(value: str):
    return (f"{value}{n}" for n in range(1, 100))


_LIST_TYPES = frozenset(("NMTOKENS", "IDREFS", "ENTITIES"))
_TEMPORAL_TYPES = frozenset(
    ("date", "dateTime", "dateTimeStamp", "time", "gYear", "gYearMonth", "gMonth", "gMonthDay", "gDay")
)


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
    elif local in _LIST_TYPES:
        # The length facets of a list count its items.
        item = _BUILTIN_VALUES[local]
        values = [" ".join([item] * _item_count(facets)), item]
    else:
        bounds = [f.value for f in reversed(facets) if f.kind in ("minInclusive", "maxInclusive")]
        values = [
            _BUILTIN_VALUES[local],
            *_VARIANTS.get(local, ()),
            *bounds,
            *_beyond_exclusive_bounds(local, facets),
            *_binary_candidates(local, facets),
        ]
    patterns = _pattern_candidates(ctx, facets)
    # A string placeholder rarely matches a pattern; a number or a date often does.
    return _unique(patterns + values if string_like else values + patterns)


def _beyond_exclusive_bounds(local: str, facets: list[Facet]) -> list[str]:
    """The nearest values inside an exclusive bound of a date, time or duration."""
    values = []
    for facet in reversed(facets):
        step = {"minExclusive": 1, "maxExclusive": -1}.get(facet.kind)
        if step is None:
            continue
        shifted = _shifted(local, facet.value, step)
        if shifted is not None:
            values.append(shifted)
    return values


_DATE = re.compile(
    r"^(-?\d{4,})(?:-(\d\d))?(?:-(\d\d))?(?:T(\d\d):(\d\d):(\d\d)(\.\d+)?)?(Z|[+-]\d\d:\d\d)?$"
)
_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)(\.\d+)?(Z|[+-]\d\d:\d\d)?$")
_DURATION = re.compile(r"^P(T?)(\d+)([YMDHS])$")


def _shifted(local: str, value: str, steps: int, unit: str | None = None) -> str | None:
    """``value`` moved ``steps`` units along its type's scale, or None when that is not possible.

    The unit is the type's smallest one -- a day for xs:date, a second for
    xs:dateTime -- unless ``unit`` says "day".
    """
    text = value.strip()
    try:
        if local == "time":
            match = _TIME.match(text)
            if match is None:
                return None
            hour, minute, second = (int(g) for g in match.group(1, 2, 3))
            total = hour * 3600 + minute * 60 + second + steps * (3600 if unit == "day" else 1)
            if not 0 <= total < 86400:
                return None
            fraction, zone = match.group(4) or "", match.group(5) or ""
            return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}{fraction}{zone}"
        if local == "duration":
            match = _DURATION.match(text)
            if match is None or int(match.group(2)) + steps < 0:
                return None
            return f"P{match.group(1)}{int(match.group(2)) + steps}{match.group(3)}"
        match = _DATE.match(text)
        if match is None:
            return None
        year, month, day, hour, minute, second, fraction, zone = match.groups()
        zone = zone or ""
        if local == "gYear" and month is None:
            moved = int(year) + steps
            return f"{moved:04d}{zone}" if 1 <= moved <= 9999 else None
        if local == "gYearMonth" and month is not None and day is None:
            months = int(year) * 12 + int(month) - 1 + steps
            return f"{months // 12:04d}-{months % 12 + 1:02d}{zone}" if 12 <= months < 120000 else None
        if local == "date" and day is not None and hour is None:
            moved = datetime.date(int(year), int(month), int(day)) + datetime.timedelta(days=steps)
            return f"{moved.isoformat()}{zone}"
        if local in ("dateTime", "dateTimeStamp") and hour is not None:
            moment = datetime.datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second)
            )
            moment += datetime.timedelta(days=steps) if unit == "day" else datetime.timedelta(seconds=steps)
            return f"{moment.isoformat()}{fraction or ''}{zone}"
    except (ValueError, OverflowError):
        return None
    return None


def _pattern_candidates(ctx: _Context, facets: list[Facet]) -> list[str]:
    min_length = _int_facet(facets, "length") or _int_facet(facets, "minLength") or 0
    values: list[str] = []
    unsupported: str | None = None
    # Facets run from the base type to the most derived one; the latter is the
    # tightest, so its pattern goes first.
    for pattern in [f.value for f in reversed(facets) if f.kind == "pattern"]:
        produced = list(samples_from_pattern(pattern, min_length))
        if not produced:
            unsupported = unsupported or pattern
        values.extend(produced)
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
    places = [0 if integer else (fraction if fraction is not None else 1)]
    if not integer and fraction is None:
        # Bounds closer together than one decimal place (0 < x < 0.05) need a
        # finer grid; it comes second, so ordinary ranges keep their short values.
        finer = min(18, _bound_places(facets) + 1)
        if finer > places[0]:
            places.append(finer)
    return _unique(value for grid in places for value in _numbers_on_grid(local, facets, grid))


def _bound_places(facets: list[Facet]) -> int:
    """Most decimal places any range facet is written with."""
    places = 0
    for facet in facets:
        if facet.kind not in _RANGE_FACETS:
            continue
        try:
            exponent = Decimal(facet.value.strip()).as_tuple().exponent
        except InvalidOperation:
            continue
        if isinstance(exponent, int):
            places = max(places, -exponent)
    return places


def _numbers_on_grid(local: str, facets: list[Facet], places: int) -> list[str]:
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
        "2026-01-01T00:00:00.000000Z",
        "2026-01-01T00:00:00.000000",
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
    """A one-element schema accepting exactly the values of ``local`` under ``facets``.

    Each pattern facet stands for one derivation step (see _by_step) and all
    of them must match, so every pattern after the first gets a restriction
    of its own: side by side in one restriction they would be alternatives.
    """
    patterns = [value for kind, value in facets if kind == "pattern"]
    body = "".join(
        f"<xs:{kind} value={quoteattr(value)}/>"
        for kind, value in facets
        if kind != "pattern" or value is patterns[0]
    )
    simple = f'<xs:simpleType><xs:restriction base="xs:{local}">{body}</xs:restriction></xs:simpleType>'
    for pattern in patterns[1:]:
        simple = (
            f"<xs:simpleType><xs:restriction>{simple}"
            f"<xs:pattern value={quoteattr(pattern)}/></xs:restriction></xs:simpleType>"
        )
    xsd = f'<xs:schema xmlns:xs="{XSD_NS}"><xs:element name="v">{simple}</xs:element></xs:schema>'
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
