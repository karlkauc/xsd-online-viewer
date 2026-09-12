"""Diagnostics for samples that come out wrong (app/usage/sample_issue.py).

The point of the feature is triage: an invalid sample whose report is full of
``schema_incomplete`` entries is the user's broken XSD, while one that is
empty or full of ``generator_limit`` entries is our bug. These tests pin that
distinction down.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import app
from app.parser.sample import (
    GENERATOR_LIMIT,
    SCHEMA_INCOMPLETE,
    SampleOptions,
    find_element,
    generate_sample_with_report,
)
from app.parser.validation import validate_xml
from app.parser.xsd_parser import parse_single
from app.usage.context import UsageTracker
from app.usage.recorder import UsageRecorder
from app.usage.sample_issue import (
    SampleIssue,
    SeenFingerprints,
    build_issue,
    decode_report,
    encode_report,
    fingerprint,
    sample_excerpts,
)

NS = "urn:t"


def _schema(body: str, *, element_form: str = "qualified") -> bytes:
    return (
        '<?xml version="1.0"?>'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'xmlns="{NS}" targetNamespace="{NS}" elementFormDefault="{element_form}">'
        f"{body}</xs:schema>"
    ).encode()


def _report_for(body: str, *, element: int = 0, **options) -> tuple[str, dict[str, int]]:
    model = parse_single(_schema(body), "t.xsd")
    xml, report = generate_sample_with_report(
        model, model.elements[element], SampleOptions(**options)
    )
    return xml, report.counts


# ---------------------------------------------------------------------------
# The generator report
# ---------------------------------------------------------------------------


def test_unresolved_type_is_schema_incomplete() -> None:
    _, counts = _report_for('<xs:element name="A" type="Nope"/>')
    assert counts == {"type_not_found": 1}


def test_unresolved_extension_base_is_reported() -> None:
    """Previously silent: the base's required children just vanish."""
    _, counts = _report_for(
        '<xs:element name="A" type="Derived"/>'
        '<xs:complexType name="Derived"><xs:complexContent>'
        '<xs:extension base="Gone">'
        '<xs:sequence><xs:element name="Own" type="xs:string"/></xs:sequence>'
        "</xs:extension></xs:complexContent></xs:complexType>"
    )
    assert counts["extension_base_not_found"] == 1


@pytest.mark.parametrize("base", ["xs:decimal", "Money"])
def test_simple_content_extension_of_a_simple_type_is_not_a_missing_base(base: str) -> None:
    """A simpleContent base is a simple type -- there is no complexType to find."""
    body = (
        '<xs:element name="A" type="Amount"/>'
        '<xs:simpleType name="Money"><xs:restriction base="xs:decimal"/></xs:simpleType>'
        '<xs:complexType name="Amount"><xs:simpleContent>'
        f'<xs:extension base="{base}">'
        '<xs:attribute name="currency" type="xs:string" use="required"/>'
        "</xs:extension></xs:simpleContent></xs:complexType>"
    )
    _, counts = _report_for(body)
    assert counts == {}


def test_unresolved_attribute_ref_is_reported() -> None:
    """Previously silent: the attribute is simply dropped."""
    _, counts = _report_for(
        '<xs:element name="A"><xs:complexType>'
        '<xs:attribute ref="missing" use="required"/>'
        "</xs:complexType></xs:element>"
    )
    assert counts["attribute_ref_not_found"] == 1


def test_unsupported_pattern_is_a_generator_limit() -> None:
    """The placeholder cannot match, so this is on us, not on the schema."""
    body = (
        '<xs:element name="A" type="Code"/>'
        '<xs:simpleType name="Code"><xs:restriction base="xs:string">'
        '<xs:pattern value="\\p{Lu}{3}"/>'
        "</xs:restriction></xs:simpleType>"
    )
    model = parse_single(_schema(body), "t.xsd")
    xml, report = generate_sample_with_report(model, model.elements[0], SampleOptions())
    assert report.counts == {"pattern_unsupported": 1}
    assert [e.category for e in report.entries] == [GENERATOR_LIMIT]
    # And the sample really is rejected, which is the whole point.
    assert not validate_xml(model, xml.encode()).is_valid


def test_depth_limit_is_reported() -> None:
    body = (
        '<xs:element name="A" type="L1"/>'
        '<xs:complexType name="L1"><xs:sequence>'
        '<xs:element name="B" type="L2"/></xs:sequence></xs:complexType>'
        '<xs:complexType name="L2"><xs:sequence>'
        '<xs:element name="C" type="xs:string"/></xs:sequence></xs:complexType>'
    )
    _, counts = _report_for(body, max_depth=1)
    assert counts == {"depth_limit": 1}


def test_wildcard_is_reported() -> None:
    _, counts = _report_for(
        '<xs:element name="A"><xs:complexType><xs:sequence>'
        '<xs:any namespace="##any"/>'
        "</xs:sequence></xs:complexType></xs:element>"
    )
    assert counts == {"wildcard_skipped": 1}


def test_strict_wildcard_without_a_matching_declaration_is_schema_incomplete() -> None:
    """Nothing in the schema may appear there -- the declaring import is missing."""
    _, counts = _report_for(
        '<xs:element name="A"><xs:complexType><xs:sequence>'
        '<xs:any namespace="urn:elsewhere" processContents="strict"/>'
        "</xs:sequence></xs:complexType></xs:element>"
    )
    assert counts == {"wildcard_without_declaration": 1}


def test_dropped_optional_subtree_replaces_its_own_entries() -> None:
    """A subtree we removed must not go on describing the output."""
    body = (
        '<xs:element name="A" type="Outer"/>'
        '<xs:complexType name="Outer"><xs:sequence>'
        '<xs:element name="Maybe" type="Outer" minOccurs="0"/>'
        "</xs:sequence></xs:complexType>"
    )
    xml, counts = _report_for(body, max_depth=3, include_optional=True)
    assert counts.get("optional_subtree_dropped", 0) >= 1
    # The depth cut happened *inside* the subtree we then threw away.
    assert "depth_limit" not in counts
    assert "recursive" in xml or "omitted" in xml


def test_clean_schema_reports_nothing(simple_xsd_bytes: bytes) -> None:
    model = parse_single(simple_xsd_bytes, "simple.xsd")
    element = find_element(model, "element:{http://example.com/simple}Person")
    assert element is not None
    xml, report = generate_sample_with_report(model, element, SampleOptions())
    assert report.is_empty and report.counts == {}
    assert validate_xml(model, xml.encode()).is_valid


# ---------------------------------------------------------------------------
# Abstract roots
# ---------------------------------------------------------------------------


ABSTRACT_BODY = (
    '<xs:element name="Head" type="xs:string" abstract="true"/>'
    '<xs:element name="Real" type="xs:string" substitutionGroup="Head"/>'
)


def test_abstract_root_substitutes() -> None:
    """An abstract root can never validate, so we swap in a member."""
    model = parse_single(_schema(ABSTRACT_BODY), "t.xsd")
    head = find_element(model, "element:{urn:t}Head")
    assert head is not None and head.abstract
    xml, report = generate_sample_with_report(model, head, SampleOptions())
    assert xml.count("Real") == 2  # open + close tag
    assert report.is_empty
    assert validate_xml(model, xml.encode()).is_valid


def test_abstract_root_without_member_is_reported() -> None:
    body = '<xs:element name="Head" type="xs:string" abstract="true"/>'
    model = parse_single(_schema(body), "t.xsd")
    head = model.elements[0]
    _, report = generate_sample_with_report(model, head, SampleOptions())
    assert report.counts == {"abstract_no_substitution": 1}
    assert [e.category for e in report.entries] == [SCHEMA_INCOMPLETE]


# ---------------------------------------------------------------------------
# Fingerprint / dedup
# ---------------------------------------------------------------------------


def _fp(**overrides) -> str:
    base = {
        "kind": "invalid",
        "app_version": "1.0.0",
        "schema_id": "abc",
        "element_id": "element:A",
        "options": (False, 1, 40),
        "error_messages": ["Element 'A': bad at line 12"],
        "reasons": ["pattern_unsupported"],
    }
    base.update(overrides)
    return fingerprint(**base)


def test_fingerprint_is_stable_and_ignores_line_numbers() -> None:
    assert _fp() == _fp()
    assert _fp(error_messages=["Element 'A': bad at line 99"]) == _fp()


def test_fingerprint_separates_versions_and_defects() -> None:
    assert _fp(app_version="1.0.1") != _fp()
    assert _fp(kind="degraded") != _fp()
    assert _fp(options=(True, 1, 40)) != _fp()
    assert _fp(error_messages=["Element 'B': other"]) != _fp()


def test_build_issue_fingerprints_the_running_version() -> None:
    """The version must be hashed in *before* the row leaves ``build_issue``.

    Enriching the row with the version afterwards would leave the fingerprint
    hashing an empty string: a defect fixed in a new release would keep
    bumping ``occurrences`` on the old row instead of starting a fresh one,
    and nobody could tell whether the fix worked.
    """
    issue = build_issue(kind="invalid", model=None)
    assert issue.app_version == __version__
    assert issue.fingerprint == fingerprint(
        kind="invalid",
        app_version=__version__,
        schema_id=None,
        element_id=None,
        options=(False, 0, 0),
        error_messages=[],
        reasons=[],
    )
    assert issue.fingerprint != build_issue(
        kind="invalid", model=None, app_version="0.0.0"
    ).fingerprint


def test_the_cloud_run_revision_tells_deploys_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    """The package version stays put across many deploys; the revision does not."""
    monkeypatch.setenv("K_REVISION", "xsdviewer-00046-abc")
    issue = build_issue(kind="invalid", model=None)
    assert issue.app_version == f"{__version__}+xsdviewer-00046-abc"
    monkeypatch.setenv("K_REVISION", "xsdviewer-00047-def")
    assert build_issue(kind="invalid", model=None).fingerprint != issue.fingerprint


def test_seen_fingerprints_skips_repeats_and_stays_bounded() -> None:
    seen = SeenFingerprints(capacity=2)
    assert seen.check_and_add("a") is True
    assert seen.check_and_add("a") is False
    seen.check_and_add("b")
    seen.check_and_add("c")  # evicts "a"
    assert seen.check_and_add("a") is True


# ---------------------------------------------------------------------------
# Report transport (untrusted: it comes back from the browser)
# ---------------------------------------------------------------------------


def test_report_survives_the_round_trip() -> None:
    _, report = generate_sample_with_report(
        parse_single(_schema('<xs:element name="A" type="Nope"/>'), "t.xsd"),
        parse_single(_schema('<xs:element name="A" type="Nope"/>'), "t.xsd").elements[0],
        SampleOptions(),
    )
    back = decode_report(encode_report(report.as_dict()))
    assert back is not None
    assert back["counts"] == {"type_not_found": 1}
    assert back["entries"][0]["reason"] == "type_not_found"


def test_oversized_report_keeps_its_counts() -> None:
    big = {
        "total": 5000,
        "counts": {"depth_limit": 5000},
        "entries": [
            {
                "reason": "depth_limit",
                "category": GENERATOR_LIMIT,
                "where": f"T{i}",
                "file_id": "f",
                "line": i,
            }
            for i in range(5000)
        ],
        "truncated": False,
    }
    encoded = encode_report(big)
    assert len(encoded) <= 8192
    back = decode_report(encoded)
    assert back is not None
    assert back["counts"] == {"depth_limit": 5000}
    assert back["total"] == 5000
    assert back["truncated"] is True
    assert len(back["entries"]) < 5000


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "!!!not base64!!!",
        base64.urlsafe_b64encode(b"not json").decode(),
        base64.urlsafe_b64encode(b'["a list"]').decode(),
    ],
)
def test_malformed_reports_are_rejected(raw: str | None) -> None:
    assert decode_report(raw) is None


def test_hostile_report_is_rebuilt_field_by_field() -> None:
    hostile = base64.urlsafe_b64encode(
        json.dumps(
            {
                "counts": {"x": True, "ok": 3},
                "entries": [{"line": "DROP TABLE", "reason": 42, "where": "w" * 9999}],
                "total": "lots",
            }
        ).encode()
    ).decode()
    back = decode_report(hostile)
    assert back is not None
    assert back["counts"] == {"ok": 3}  # booleans and non-str keys dropped
    assert back["entries"][0] == {
        "reason": None,
        "category": None,
        "where": "w" * 200,
        "file_id": None,
        "line": None,
    }
    assert back["total"] == 1


# ---------------------------------------------------------------------------
# Excerpts: lines around the offending declarations, never whole files
# ---------------------------------------------------------------------------


def test_excerpts_cover_the_error_and_omit_the_rest() -> None:
    body = "".join(f'<xs:element name="E{i}" type="xs:string"/>' for i in range(60))
    model = parse_single(
        _schema(body).replace(b"><xs:element", b">\n<xs:element"), "t.xsd"
    )
    target = model.elements[40]
    entries = [{"file_id": target.source_ref.file_id, "line": target.source_ref.line}]
    excerpts = sample_excerpts(model, [], entries)
    assert len(excerpts) == 1
    assert excerpts[0]["file"] == "t.xsd"
    assert 'name="E40"' in excerpts[0]["snippet"]
    assert 'name="E0"' not in excerpts[0]["snippet"]


def test_excerpts_are_capped() -> None:
    body = "".join(f'<xs:element name="E{i}" type="xs:string"/>' for i in range(400))
    model = parse_single(_schema(body).replace(b"><xs:element", b">\n<xs:element"), "t.xsd")
    entries = [
        {"file_id": e.source_ref.file_id, "line": e.source_ref.line}
        for e in model.elements
        if e.source_ref
    ]
    excerpts = sample_excerpts(model, [], entries, max_chars=500)
    assert sum(len(x["snippet"]) for x in excerpts) <= 500


def test_build_issue_keeps_the_document_but_not_the_schema() -> None:
    model = parse_single(_schema('<xs:element name="A" type="xs:string"/>'), "t.xsd")
    issue = build_issue(
        kind="invalid",
        model=model,
        element_id="element:A",
        sample_xml="<A>x</A>",
        errors=[],
        report={"total": 0, "counts": {}, "entries": [], "truncated": False},
        app_version="1.0.0",
    )
    assert issue.sample_xml == "<A>x</A>"
    assert issue.schema_name == "t.xsd"
    assert issue.schema_bytes and issue.schema_bytes > 0
    # No column anywhere holds the schema source itself.
    row = " ".join(str(v) for v in issue.as_row() if isinstance(v, str))
    assert "xs:schema" not in row


# ---------------------------------------------------------------------------
# End to end through the API
# ---------------------------------------------------------------------------


class IssueRecorder(UsageRecorder):
    def __init__(self) -> None:
        super().__init__("postgresql://fake")
        self.issues: list[SampleIssue] = []

    def record(self, event: SampleIssue) -> bool:  # type: ignore[override]
        self.issues.append(event)
        return True

    async def drain(self, timeout: float = 2.0) -> bool:
        return True


class NullRecorder(UsageRecorder):
    def __init__(self) -> None:
        super().__init__("postgresql://fake")

    def record(self, event: object) -> bool:  # type: ignore[override]
        return True

    async def drain(self, timeout: float = 2.0) -> bool:
        return True


@pytest.fixture
def issues() -> Iterator[IssueRecorder]:
    rec = IssueRecorder()
    app.state.usage = UsageTracker(NullRecorder(), geoip=None, hash_secret="test", issues=rec)
    try:
        yield rec
    finally:
        del app.state.usage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={"user-agent": "pytest-browser"})


def _load(client: TestClient, xsd: bytes) -> str:
    r = client.post("/api/schema/text", json={"filename": "t.xsd", "content": xsd.decode()})
    assert r.status_code == 200
    return r.json()["schema_id"]


def _sample_then_validate(
    client: TestClient, schema_id: str, element_id: str, optional: bool = False
) -> None:
    """What the browser does: fetch the sample, then check it, report in hand."""
    params = {"element": element_id}
    if optional:
        params["optional"] = "true"
    got = client.get(f"/api/schema/{schema_id}/sample", params=params)
    assert got.status_code == 200
    client.post(
        f"/api/schema/{schema_id}/validate/text",
        json={
            "content": got.text,
            "filename": "t-sample.xml",
            "origin": "sample",
            "sample": {
                "element_id": element_id,
                "include_optional": optional,
                "generation_ms": 5,
                "report": got.headers["X-Sample-Report"],
            },
        },
    )


PATTERN_XSD = _schema(
    '<xs:element name="A" type="Code"/>'
    '<xs:simpleType name="Code"><xs:restriction base="xs:string">'
    '<xs:pattern value="\\p{Lu}{3}"/>'
    "</xs:restriction></xs:simpleType>"
)


def test_invalid_sample_is_recorded_with_the_reason(
    client: TestClient, issues: IssueRecorder
) -> None:
    schema_id = _load(client, PATTERN_XSD)
    _sample_then_validate(client, schema_id, "element:{urn:t}A")

    (issue,) = issues.issues
    assert issue.kind == "invalid"
    assert issue.error_count == 1
    assert issue.element_qname == "{urn:t}A"
    assert issue.sample_xml is not None and "<ns1:A" in issue.sample_xml
    assert json.loads(issue.report)["counts"] == {"pattern_unsupported": 1}
    assert "pattern" in json.loads(issue.errors)[0]["message"]
    # The offending declaration is quoted, the whole schema is not.
    assert "xs:pattern" in json.loads(issue.xsd_excerpts)[0]["snippet"]
    assert issue.visitor_hash and issue.app_version == __version__


def test_a_repeated_defect_still_counts_without_its_payload(
    client: TestClient, issues: IssueRecorder
) -> None:
    """A repeat must bump ``occurrences``, or the table cannot rank defects by hits.

    Only the fingerprint and the small metadata travel again; the upsert's
    conflict branch does the counting.
    """
    schema_id = _load(client, PATTERN_XSD)
    _sample_then_validate(client, schema_id, "element:{urn:t}A")
    _sample_then_validate(client, schema_id, "element:{urn:t}A")
    first, repeat = issues.issues
    assert repeat.fingerprint == first.fingerprint
    assert first.sample_xml is not None and first.errors is not None
    assert (
        repeat.sample_xml,
        repeat.errors,
        repeat.report,
        repeat.diagnostics,
        repeat.xsd_excerpts,
    ) == (None, None, None, None, None)


def test_a_clean_sample_records_nothing(
    client: TestClient, issues: IssueRecorder, simple_xsd_bytes: bytes
) -> None:
    schema_id = _load(client, simple_xsd_bytes)
    _sample_then_validate(client, schema_id, "element:{http://example.com/simple}Person")
    assert issues.issues == []


def test_valid_but_degraded_sample_is_recorded(
    client: TestClient, issues: IssueRecorder
) -> None:
    """We left out an optional wildcard: still valid, but not what was asked for."""
    xsd = _schema(
        '<xs:element name="A"><xs:complexType><xs:sequence>'
        '<xs:any namespace="##any" processContents="lax" minOccurs="0"/>'
        "</xs:sequence></xs:complexType></xs:element>"
    )
    schema_id = _load(client, xsd)
    _sample_then_validate(client, schema_id, "element:{urn:t}A", optional=True)
    (issue,) = issues.issues
    assert issue.kind == "degraded"
    assert issue.error_count == 0
    assert json.loads(issue.report)["counts"] == {"wildcard_skipped": 1}


def test_uncompilable_schema_is_kept_apart(client: TestClient, issues: IssueRecorder) -> None:
    """XSD 1.1 is libxml2's limit, not a generator defect."""
    xsd = _schema(
        '<xs:element name="A"><xs:complexType>'
        '<xs:sequence><xs:element name="B" type="xs:int"/></xs:sequence>'
        '<xs:assert test="B > 0"/>'
        "</xs:complexType></xs:element>"
    )
    schema_id = _load(client, xsd)
    _sample_then_validate(client, schema_id, "element:{urn:t}A")
    (issue,) = issues.issues
    assert issue.kind == "setup_error"
    assert issue.xsd_version in ("1.1", "unknown")
    # Why it does not compile is the whole point of the row.
    (error,) = json.loads(issue.errors)
    assert error["kind"] == "schema-setup"
    assert error["message"].startswith("the schema uses XSD 1.1")


def test_an_uncompilable_schema_is_one_defect_whatever_the_root(
    client: TestClient, issues: IssueRecorder
) -> None:
    """The schema is broken, not a sample: every root and option used to open its own row."""
    xsd = _schema(
        '<xs:element name="A" type="Missing"/>'
        '<xs:element name="B" type="xs:string"/>'
    )
    schema_id = _load(client, xsd)
    _sample_then_validate(client, schema_id, "element:{urn:t}B")
    _sample_then_validate(client, schema_id, "element:{urn:t}B", optional=True)
    first, repeat = issues.issues
    assert first.kind == repeat.kind == "setup_error"
    assert repeat.fingerprint == first.fingerprint
    assert repeat.sample_xml is None  # counted, not shipped again


def test_direct_api_use_without_a_report_records_nothing(
    client: TestClient, issues: IssueRecorder
) -> None:
    """Only the app's own sample check is recorded; plain validation is not."""
    schema_id = _load(client, PATTERN_XSD)
    got = client.get(f"/api/schema/{schema_id}/sample", params={"element": "element:{urn:t}A"})
    r = client.post(
        f"/api/schema/{schema_id}/validate/text",
        json={"content": got.text, "filename": "x.xml", "origin": "text"},
    )
    assert r.status_code == 200 and r.json()["is_valid"] is False
    assert issues.issues == []
