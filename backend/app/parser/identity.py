"""Post-passes: resolve ``xs:keyref/@refer`` to the identity constraint it
names, and an XSD 1.1 constraint reference (``<xs:key ref="…"/>``) to its
definition.

Runs after every element in the model has been parsed (identity constraints
are scanned per-element during parsing, so a keyref's target may not have
been parsed yet at the point the keyref itself is seen — e.g. it can sit on
an element that comes later in document order, or in another file).
"""

from __future__ import annotations

from app.parser.model import Diagnostic, IdentityConstraint, SchemaModel
from app.parser.walk import iter_elements


def resolve_constraint_refs(model: SchemaModel, diagnostics: list[Diagnostic]) -> None:
    """Give every constraint reference the selector and fields of its definition.

    ``ref_id`` was resolved through the namespaces in scope where the
    reference is written; when that names no definition of the same kind, a
    unique local-name match is taken instead. A reference that still finds
    nothing keeps its empty selector, loses its ``ref_id`` and is reported.
    """
    definitions: dict[str, IdentityConstraint] = {}
    by_local_name: dict[tuple[str, str], list[IdentityConstraint]] = {}
    references: list[IdentityConstraint] = []
    for element in iter_elements(model):
        for constraint in element.identity_constraints:
            if constraint.ref:
                references.append(constraint)
            else:
                definitions[constraint.id] = constraint
                by_local_name.setdefault((constraint.kind, constraint.name), []).append(constraint)

    for reference in references:
        target = definitions.get(reference.ref_id or "")
        if target is None or target.kind != reference.kind:
            candidates = by_local_name.get((reference.kind, reference.name), [])
            target = candidates[0] if len(candidates) == 1 else None
        if target is None:
            reference.ref_id = None
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=(
                        f"{reference.kind} reference {reference.ref!r} names no "
                        f"xs:{reference.kind} the loaded files declare"
                    ),
                    file_id=reference.source_ref.file_id if reference.source_ref else None,
                    line=reference.source_ref.line if reference.source_ref else None,
                )
            )
            continue
        reference.ref_id = target.id
        reference.qname = target.qname
        reference.selector = target.selector
        reference.fields = list(target.fields)
        reference.field_xpath_default_namespaces = list(target.field_xpath_default_namespaces)
        reference.xpath_default_namespace = target.xpath_default_namespace
        reference.refer = target.refer
        reference.refer_id = target.refer_id


def link_keyrefs(model: SchemaModel, diagnostics: list[Diagnostic]) -> None:
    """Fill in ``refer_id`` on every ``keyref`` identity constraint in
    ``model``, mutating the constraints in place.

    A keyref already carrying a ``refer_id`` (resolved via the namespace
    declarations in scope where it was written) is left untouched. Otherwise
    we fall back to a unique local-name match across every ``key``/``unique``
    constraint in the model — this recovers cases where the ``refer`` prefix
    doesn't resolve through the in-scope namespaces but the name is
    unambiguous. If neither works, ``refer_id`` stays ``None`` and a warning
    diagnostic is appended.
    """
    by_id: dict[str, IdentityConstraint] = {}
    by_local_name: dict[str, list[IdentityConstraint]] = {}
    for element in iter_elements(model):
        for constraint in element.identity_constraints:
            # A reference is its definition used once more, not another key.
            if constraint.kind == "keyref" or constraint.ref:
                continue
            by_id[constraint.id] = constraint
            by_local_name.setdefault(constraint.name, []).append(constraint)

    for element in iter_elements(model):
        for constraint in element.identity_constraints:
            if constraint.kind != "keyref" or not constraint.refer:
                continue
            if constraint.ref and constraint.ref_id is not None:
                continue  # takes its definition's target, reported there if unknown
            if constraint.refer_id is not None and constraint.refer_id in by_id:
                continue
            local_name = (constraint.refer or "").rpartition(":")[2]
            candidates = by_local_name.get(local_name, [])
            if len(candidates) == 1:
                constraint.refer_id = candidates[0].id
                continue
            constraint.refer_id = None
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    message=(
                        f"keyref {constraint.name!r} refers to unknown key "
                        f"{constraint.refer!r}"
                    ),
                    file_id=constraint.source_ref.file_id if constraint.source_ref else None,
                    line=constraint.source_ref.line if constraint.source_ref else None,
                )
            )
