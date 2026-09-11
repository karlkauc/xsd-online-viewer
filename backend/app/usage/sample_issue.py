"""Diagnostics for XML sample documents that do not come out right.

The generator in ``app.parser.sample`` is best-effort: it walks a content
model and fills in placeholders. When the result fails its schema check we
want to know *why* — and specifically whether the generator gave up where a
better one need not (a bug we can fix) or the schema simply never offered
what it needed (nothing to fix). One row of ``sample_issue`` carries enough
context to answer that without a reproduction from the user:

* the validator's errors, in full;
* the generator's own report of every spot it had to fudge, classified into
  ``generator_limit`` and ``schema_incomplete``;
* the parser's diagnostics about the schema itself;
* the generated document — synthetic data, so it is kept whole;
* short excerpts of the XSD lines around the declarations the errors and
  the report point at. Schema files are never stored in full.

Rows are deduplicated on a fingerprint, so a defect that thousands of
visitors hit is one row with a counter, and the table ranks itself by how
much each bug actually matters.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
from typing import Any

from app import release_version
from app.parser.model import SchemaModel
from app.parser.validation import ValidationErrorItem

# A generated document is synthetic, but a pathological schema could still
# produce a huge one; cap it so a single row can never wedge the writer.
MAX_SAMPLE_CHARS = 1_000_000
# Lines of XSD kept on each side of a declaration an error points at.
EXCERPT_CONTEXT_LINES = 8
MAX_EXCERPT_CHARS = 16_384
# Per-snippet cap too, so one minified line cannot spend the whole budget and
# crowd out the other locations that are at fault.
MAX_SNIPPET_CHARS = 4_000
MAX_TRACEBACK_CHARS = 8_000
# The report travels to the browser in a response header and back in the
# validate payload, so it has to stay small and be treated as untrusted.
MAX_REPORT_ENTRIES = 200
MAX_REPORT_HEADER_BYTES = 8_192
_MAX_FIELD_CHARS = 200

_JSONB_COLUMNS = frozenset({"errors", "report", "diagnostics", "xsd_excerpts"})


@dataclass(slots=True)
class SampleIssue:
    """One row of the ``sample_issue`` table (column order = field order)."""

    fingerprint: str
    kind: str
    app_version: str | None = None
    visitor_hash: str | None = None
    country_code: str | None = None
    device: str | None = None
    schema_id: str | None = None
    schema_name: str | None = None
    target_namespace: str | None = None
    xsd_version: str | None = None
    file_count: int | None = None
    schema_bytes: int | None = None
    element_id: str | None = None
    element_qname: str | None = None
    include_optional: bool | None = None
    repeat_count: int | None = None
    max_depth: int | None = None
    generation_ms: int | None = None
    sample_bytes: int | None = None
    sample_truncated: bool | None = None
    error_count: int | None = None
    degradation_count: int | None = None
    errors: str | None = None  # jsonb
    report: str | None = None  # jsonb
    diagnostics: str | None = None  # jsonb
    xsd_excerpts: str | None = None  # jsonb
    sample_xml: str | None = None
    traceback: str | None = None

    def as_row(self) -> tuple:
        return tuple(getattr(self, f.name) for f in fields(self))

    def without_payload(self) -> SampleIssue:
        """The same defect minus the bulky columns: enough to count a repeat."""
        return replace(
            self,
            errors=None,
            report=None,
            diagnostics=None,
            xsd_excerpts=None,
            sample_xml=None,
            traceback=None,
        )


COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(SampleIssue))

_PLACEHOLDERS = ", ".join(
    "%s::jsonb" if column in _JSONB_COLUMNS else "%s" for column in COLUMNS
)

# A repeat visit bumps the counter instead of adding a row, so the table stays
# small and ``occurrences`` ranks the defects by how often they are hit.
INSERT_SQL = (
    f"INSERT INTO sample_issue ({', '.join(COLUMNS)}) VALUES ({_PLACEHOLDERS}) "
    "ON CONFLICT (fingerprint) DO UPDATE SET "
    "occurrences = sample_issue.occurrences + 1, last_seen_at = now()"
)


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

_DIGIT_RUN = re.compile(r"\d+")


def _normalise(message: str) -> str:
    """Collapse digit runs so line numbers and counts do not split a defect."""
    return _DIGIT_RUN.sub("#", message.strip())


def fingerprint(
    *,
    kind: str,
    app_version: str | None,
    schema_id: str | None,
    element_id: str | None,
    options: tuple[bool, int, int] | None,
    error_messages: Iterable[str],
    reasons: Iterable[str],
) -> str:
    """Stable id for "this defect, in this app version".

    ``app_version`` is part of it on purpose: without it a row whose bug was
    fixed last release keeps counting up, and nobody can tell whether the fix
    worked.
    """
    parts = [
        kind,
        app_version or "",
        schema_id or "",
        element_id or "",
        repr(options),
        "|".join(sorted(_normalise(m) for m in error_messages)),
        "|".join(sorted(set(reasons))),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class SeenFingerprints:
    """Bounded set of fingerprints this process already wrote.

    ``ON CONFLICT`` keeps the table small but still ships the whole payload to
    Postgres first; skipping the insert outright is what actually saves the
    bandwidth on a defect that every visitor trips over.
    """

    def __init__(self, capacity: int = 512) -> None:
        self._capacity = capacity
        self._seen: OrderedDict[str, None] = OrderedDict()

    def check_and_add(self, value: str) -> bool:
        """True if ``value`` is new to this process (and remembers it)."""
        if value in self._seen:
            self._seen.move_to_end(value)
            return False
        self._seen[value] = None
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return True


# ---------------------------------------------------------------------------
# XSD excerpts
# ---------------------------------------------------------------------------


def sample_excerpts(
    model: SchemaModel,
    errors: Iterable[ValidationErrorItem] = (),
    entries: Iterable[dict[str, Any]] = (),
    *,
    context_lines: int = EXCERPT_CONTEXT_LINES,
    max_chars: int = MAX_EXCERPT_CHARS,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
) -> list[dict[str, Any]]:
    """XSD lines around the declarations the errors and the report point at.

    Deliberately *not* the whole schema: only what is needed to see the
    declaration that produced a bad sample.
    """
    wanted: dict[str, set[int]] = {}
    for error in errors:
        ref = error.xsd_ref
        if ref is not None and ref.file_id and ref.line:
            wanted.setdefault(ref.file_id, set()).add(ref.line)
    for entry in entries:
        file_id, line = entry.get("file_id"), entry.get("line")
        if isinstance(file_id, str) and isinstance(line, int) and file_id and line > 0:
            wanted.setdefault(file_id, set()).add(line)
    if not wanted:
        return []

    by_id = {f.id: f for f in model.files}
    excerpts: list[dict[str, Any]] = []
    budget = max_chars
    for file_id, line_numbers in wanted.items():
        source = by_id.get(file_id)
        if source is None or source.content is None:
            continue
        lines = source.content.splitlines()
        for start, end in _merge_windows(sorted(line_numbers), context_lines, len(lines)):
            if budget <= 0:
                break
            snippet = "\n".join(lines[start - 1 : end])[: min(budget, max_snippet_chars)]
            budget -= len(snippet)
            excerpts.append(
                {
                    "file": source.filename,
                    "first_line": start,
                    "last_line": end,
                    "snippet": snippet,
                }
            )
    return excerpts


def _merge_windows(
    line_numbers: list[int], context: int, total_lines: int
) -> list[tuple[int, int]]:
    """Turn line numbers into merged, 1-based, inclusive line ranges."""
    windows: list[tuple[int, int]] = []
    for line in line_numbers:
        start = max(1, line - context)
        end = min(total_lines, line + context)
        if end < start:
            continue
        if windows and start <= windows[-1][1] + 1:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
    return windows


# ---------------------------------------------------------------------------
# Building a row
# ---------------------------------------------------------------------------


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def build_issue(
    *,
    kind: str,
    model: SchemaModel | None,
    element_id: str | None = None,
    element_qname: str | None = None,
    include_optional: bool | None = None,
    repeat: int | None = None,
    max_depth: int | None = None,
    generation_ms: int | None = None,
    sample_xml: str | None = None,
    errors: list[ValidationErrorItem] | None = None,
    report: dict[str, Any] | None = None,
    traceback: str | None = None,
    app_version: str | None = None,
) -> SampleIssue:
    """Assemble a row. Pure — the caller supplies every piece of context.

    ``report`` is a ``SampleReport.as_dict()`` payload, which may have made a
    round trip through the browser; treat it as data, never as truth.

    ``app_version`` defaults to the running release (version plus Cloud Run
    revision) and must be settled *here*, because the fingerprint hashes it:
    filling it in after the fact would fingerprint an empty version, and a
    defect fixed in a new release would keep bumping the old row's counter
    instead of starting a fresh one.
    """
    version = app_version if app_version is not None else release_version()
    errors = errors or []
    entries = report.get("entries") or [] if report else []
    reasons = list((report.get("counts") or {}).keys()) if report else []

    document = sample_xml or ""
    truncated = len(document) > MAX_SAMPLE_CHARS
    if truncated:
        document = document[:MAX_SAMPLE_CHARS]

    main = None
    if model is not None:
        main = next((f for f in model.files if f.relationship == "main"), None)

    # A schema that does not compile is one defect however it was reached;
    # otherwise every root and option combination would open a row of its own.
    schema_defect = kind == "setup_error"
    return SampleIssue(
        fingerprint=fingerprint(
            kind=kind,
            app_version=version,
            schema_id=model.schema_id if model is not None else None,
            element_id=None if schema_defect else element_id,
            options=(
                None
                if schema_defect
                else (bool(include_optional), int(repeat or 0), int(max_depth or 0))
            ),
            error_messages=[e.message for e in errors],
            reasons=[] if schema_defect else reasons,
        ),
        kind=kind,
        app_version=version,
        schema_id=model.schema_id if model is not None else None,
        schema_name=main.filename if main is not None else None,
        target_namespace=model.target_namespace if model is not None else None,
        xsd_version=model.xsd_version if model is not None else None,
        file_count=len(model.files) if model is not None else None,
        schema_bytes=(
            sum(len(f.content or "") for f in model.files) if model is not None else None
        ),
        element_id=element_id,
        element_qname=element_qname,
        include_optional=include_optional,
        repeat_count=repeat,
        max_depth=max_depth,
        generation_ms=generation_ms,
        sample_bytes=len(sample_xml) if sample_xml is not None else None,
        sample_truncated=truncated,
        error_count=len(errors),
        degradation_count=int(report.get("total") or len(entries)) if report else None,
        errors=_json([e.model_dump(mode="json") for e in errors]) if errors else None,
        report=_json(report) if report is not None else None,
        diagnostics=(
            _json([d.model_dump(mode="json") for d in model.diagnostics])
            if model is not None and model.diagnostics
            else None
        ),
        xsd_excerpts=(
            _json(sample_excerpts(model, errors, entries)) if model is not None else None
        ),
        sample_xml=document or None,
        traceback=traceback[:MAX_TRACEBACK_CHARS] if traceback else None,
    )


# ---------------------------------------------------------------------------
# Header transport
# ---------------------------------------------------------------------------


def encode_report(report: dict[str, Any], max_bytes: int = MAX_REPORT_HEADER_BYTES) -> str:
    """Pack a report into a base64url header value, shrinking it until it fits.

    ``counts`` is never dropped, so even a heavily truncated report still says
    what went wrong and how often — only the individual locations are lost.
    """
    limit = len(report.get("entries") or [])
    while True:
        payload = dict(report)
        entries = (report.get("entries") or [])[:limit]
        payload["entries"] = entries
        payload["truncated"] = bool(report.get("truncated")) or limit < len(
            report.get("entries") or []
        )
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii")
        if len(encoded) <= max_bytes or limit == 0:
            return encoded
        limit //= 2


def decode_report(raw: str | None) -> dict[str, Any] | None:
    """Parse a report that came back from the browser. Never raises.

    Everything here is attacker-controlled, so the shape is rebuilt field by
    field rather than trusted: unknown keys are dropped, strings are capped,
    and anything malformed yields ``None``.
    """
    if not raw:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        parsed = json.loads(decoded)
    except (ValueError, binascii.Error, UnicodeEncodeError):
        return None
    if not isinstance(parsed, dict):
        return None

    counts: dict[str, int] = {}
    for reason, count in (parsed.get("counts") or {}).items():
        if isinstance(reason, str) and isinstance(count, int) and not isinstance(count, bool):
            counts[reason[:_MAX_FIELD_CHARS]] = max(0, min(count, 1_000_000))

    entries: list[dict[str, Any]] = []
    for entry in (parsed.get("entries") or [])[:MAX_REPORT_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        line = entry.get("line")
        entries.append(
            {
                "reason": _text(entry.get("reason")),
                "category": _text(entry.get("category")),
                "where": _text(entry.get("where")),
                "file_id": _text(entry.get("file_id")),
                "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
            }
        )

    total = parsed.get("total")
    return {
        "total": total if isinstance(total, int) and not isinstance(total, bool) else len(entries),
        "counts": counts,
        "entries": entries,
        "truncated": bool(parsed.get("truncated")),
    }


def _text(value: Any) -> str | None:
    return value[:_MAX_FIELD_CHARS] if isinstance(value, str) else None
