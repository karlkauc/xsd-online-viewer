"""Post-pass: resolve ``xs:keyref/@refer`` to the identity constraint it
names.

Runs after every element in the model has been parsed (identity constraints
are scanned per-element during parsing, so a keyref's target may not have
been parsed yet at the point the keyref itself is seen — e.g. it can sit on
an element that comes later in document order, or in another file).
"""

from __future__ import annotations

from app.parser.model import Diagnostic, IdentityConstraint, SchemaModel
from app.parser.walk import iter_elements


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
            if constraint.kind == "keyref":
                continue
            by_id[constraint.id] = constraint
            by_local_name.setdefault(constraint.name, []).append(constraint)

    for element in iter_elements(model):
        for constraint in element.identity_constraints:
            if constraint.kind != "keyref" or not constraint.refer:
                continue
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
