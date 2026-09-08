"""Post-pass: classify ID/IDREF/IDREFS roles for elements and attributes.

Runs right after ``identity.link_keyrefs`` in ``XsdParser.parse()`` — no
other prerequisite pass.

XSD binds an ``IDREF``/``IDREFS`` value to *any* ``xs:ID`` in the document,
not to a specific declaration, so there is nothing to resolve to a target
here — this module only classifies what role, if any, a declaration's type
plays. The frontend uses ``id_role`` to render "ID reference" / "Referenced
by IDREF" sections for elements and attributes typed (directly, or through a
chain of named/inline simple types) as ``xs:ID``, ``xs:IDREF`` or
``xs:IDREFS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.model import (
    XSD_NS,
    AttributeDecl,
    ComplexType,
    ElementDecl,
    IdRole,
    SchemaModel,
    SimpleType,
)
from app.parser.walk import iter_attributes, iter_elements


def expand_qname(qname: str, namespaces: dict[str, str]) -> str:
    """Expand a QName (``"prefix:local"`` or unprefixed ``"local"``) to Clark
    form (``"{namespace}local"``) using ``namespaces`` (prefix -> URI, with
    the default namespace under key ``""``).

    Falls back to the bare local name when the prefix — or, for an
    unprefixed name, the default namespace — isn't declared in
    ``namespaces``. This also lets a bare local name match an index entry
    for a type with no namespace at all.
    """
    prefix, sep, local = qname.rpartition(":")
    uri = namespaces.get(prefix) if sep else namespaces.get("")
    return f"{{{uri}}}{local}" if uri else local


@dataclass
class _Index:
    """Lookup tables built once per ``apply_id_roles`` call."""

    namespaces: dict[str, str]
    builtin_roles: dict[str, IdRole]
    simple_by_clark: dict[str, SimpleType] = field(default_factory=dict)
    simple_by_local: dict[str, SimpleType] = field(default_factory=dict)
    complex_by_clark: dict[str, ComplexType] = field(default_factory=dict)
    complex_by_local: dict[str, ComplexType] = field(default_factory=dict)


def _declaring_namespace(
    decl: SimpleType | ComplexType,
    file_namespaces: dict[str, str | None],
    model_target_namespace: str | None,
) -> str | None:
    """The target namespace a named type was actually declared under.

    A multi-file model can have files with different target namespaces (an
    ``xs:import``ed schema, most commonly), so a type must be indexed under
    *its own* file's target namespace — not the model's primary one, or a
    same-named type from a different namespace would collide with it. Falls
    back to the model's target namespace only when the type's file is
    unknown (defensive; every parsed type carries a ``source_ref``). When
    the file *is* known but declares no target namespace of its own (e.g. a
    chameleon-included file), that ``None`` is returned as-is — the loader
    already resolves such a file's effective namespace onto
    ``target_namespace`` before this pass runs (via ``target_ns_hint``), so
    ``file_namespaces`` never actually holds ``None`` for one in practice.
    Mirrors ``sample.py``'s ``_Context.namespace_of``.
    """
    file_id = decl.source_ref.file_id if decl.source_ref else None
    if file_id is not None and file_id in file_namespaces:
        return file_namespaces[file_id]
    return model_target_namespace


def _build_index(model: SchemaModel, xsd_ns: str) -> _Index:
    file_namespaces: dict[str, str | None] = {f.id: f.target_namespace for f in model.files}
    index = _Index(
        namespaces=model.namespaces,
        builtin_roles={
            f"{{{xsd_ns}}}ID": "id",
            f"{{{xsd_ns}}}IDREF": "idref",
            f"{{{xsd_ns}}}IDREFS": "idrefs",
        },
    )
    for st in model.simple_types:
        if not st.name:
            continue
        ns = _declaring_namespace(st, file_namespaces, model.target_namespace)
        clark = f"{{{ns}}}{st.name}" if ns else st.name
        index.simple_by_clark.setdefault(clark, st)
        index.simple_by_local.setdefault(st.name, st)
    for ct in model.complex_types:
        if not ct.name:
            continue
        ns = _declaring_namespace(ct, file_namespaces, model.target_namespace)
        clark = f"{{{ns}}}{ct.name}" if ns else ct.name
        index.complex_by_clark.setdefault(clark, ct)
        index.complex_by_local.setdefault(ct.name, ct)
    return index


def classify_simple(
    st: SimpleType, index: _Index, seen: frozenset[str]
) -> IdRole | None:
    """Classify the ID/IDREF role of an (anonymous or named) simple type.

    ``seen`` carries the ids of simple types already visited on the current
    restriction/list/union path, guarding against a restriction cycle
    (``A`` restricts ``B`` restricts ``A``) recursing forever.
    """
    if st.id in seen:
        return None
    seen = seen | {st.id}

    if st.derivation == "restriction":
        if st.base is not None:
            return classify_type_ref(st.base, index, seen)
        if st.member_inline:
            # Parser quirk (see xsd_parser._parse_simple_type): a restriction
            # whose base is a nested anonymous <xs:simpleType> (no @base
            # attribute) stores that inline type in member_inline[0] with
            # base=None.
            return classify_simple(st.member_inline[0], index, seen)
        return None

    if st.derivation == "list":
        if st.item_type is not None:
            item_role = classify_type_ref(st.item_type, index, seen)
        elif st.item_inline is not None:
            item_role = classify_simple(st.item_inline, index, seen)
        else:
            item_role = None
        return "idrefs" if item_role is not None else None

    if st.derivation == "union":
        roles = [classify_type_ref(member, index, seen) for member in st.member_types]
        roles += [classify_simple(member, index, seen) for member in st.member_inline]
        if "id" in roles:
            return "id"
        if "idref" in roles or "idrefs" in roles:
            return "idrefs"
        return None

    return None  # derivation == "atomic": no restriction/list/union present


def classify_type_ref(
    qname: str, index: _Index, seen: frozenset[str] = frozenset()
) -> IdRole | None:
    """Classify the ID/IDREF role a type *reference* (a ``type="..."``
    QName) resolves to: builtin XSD type -> named simple type -> named
    complex type with simple content (via its ``simple_content_base``).

    ``seen`` also guards the complex -> ``simple_content_base`` -> complex
    hop: two named complex types whose ``simpleContent`` extensions name
    each other (illegal per XSD, but not rejected by the parser) would
    otherwise recurse forever. It shares one set with ``classify_simple``'s
    guard since declaration ids are unique across the whole model.
    """
    clark = expand_qname(qname, index.namespaces)
    role = index.builtin_roles.get(clark)
    if role is not None:
        return role

    local = qname.rpartition(":")[2]
    st = index.simple_by_clark.get(clark) or index.simple_by_local.get(local)
    if st is not None:
        return classify_simple(st, index, seen)

    ct = index.complex_by_clark.get(clark) or index.complex_by_local.get(local)
    if ct is not None and ct.content_kind == "simple" and ct.simple_content_base:
        if ct.id in seen:
            return None
        return classify_type_ref(ct.simple_content_base, index, seen | {ct.id})

    return None


def _classify_element(element: ElementDecl, index: _Index) -> IdRole | None:
    if element.ref is not None:
        # A ref particle carries no type of its own — the frontend resolves
        # the role through the target of resolveElementRef.
        return None
    if element.type_name is not None:
        return classify_type_ref(element.type_name, index)
    if element.type_inline_simple is not None:
        return classify_simple(element.type_inline_simple, index, frozenset())
    ct = element.type_inline_complex
    if ct is not None and ct.content_kind == "simple" and ct.simple_content_base:
        return classify_type_ref(ct.simple_content_base, index)
    return None


def _classify_attribute(attribute: AttributeDecl, index: _Index) -> IdRole | None:
    if attribute.type_name is not None:
        return classify_type_ref(attribute.type_name, index)
    if attribute.type_inline is not None:
        return classify_simple(attribute.type_inline, index, frozenset())
    return None


def apply_id_roles(model: SchemaModel) -> None:
    """Set ``id_role`` on every element and attribute reachable from
    ``model``, mutating the declarations in place.

    Must run after every element/attribute in the model has been parsed —
    a named simple/complex type referenced by ``type="..."`` may be declared
    anywhere in the model, including after the point where it's used.
    """
    index = _build_index(model, XSD_NS)
    for element in iter_elements(model):
        element.id_role = _classify_element(element, index)
    for attribute in iter_attributes(model):
        attribute.id_role = _classify_attribute(attribute, index)
