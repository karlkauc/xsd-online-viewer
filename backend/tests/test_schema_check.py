"""The second reading of the schema itself (GET /api/schema/{id}/check).

libxml2 compiles every schema below without complaint; the W3C test suite
(tools/w3c_suite.py) lists them as invalid.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser.validation import build_xmlschema, check_schema
from app.parser.xsd_parser import parse_files_map, parse_single

pytest.importorskip("xmlschema")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


XS = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
ILLEGAL_RESTRICTION = f"""<xs:schema {XS}>
  <xs:complexType name="Base"><xs:sequence>
    <xs:element name="a" type="xs:string"/>
  </xs:sequence></xs:complexType>
  <xs:complexType name="Derived"><xs:complexContent><xs:restriction base="Base">
    <xs:sequence><xs:element name="b" type="xs:string"/></xs:sequence>
  </xs:restriction></xs:complexContent></xs:complexType>
  <xs:element name="R" type="Derived"/>
</xs:schema>"""
VALID = f'<xs:schema {XS}><xs:element name="R" type="xs:int"/></xs:schema>'


def _check(text: str):  # noqa: ANN202
    return check_schema(parse_single(text.encode(), "s.xsd"))


def test_a_restriction_that_is_none_is_found_where_libxml2_sees_nothing() -> None:
    model = parse_single(ILLEGAL_RESTRICTION.encode(), "s.xsd")
    build_xmlschema(model)  # libxml2 compiles it
    result = check_schema(model)
    assert result.status == "findings" and result.version == "1.0"
    [finding] = result.findings
    assert "illegal restriction" in finding.message
    assert finding.file_id == model.files[0].id and finding.line == 5


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '<xs:simpleType name="T"><xs:restriction base="xs:integer">'
            '<xs:fractionDigits value="2"/></xs:restriction></xs:simpleType>',
            "fractionDigits",
        ),
        (
            '<xs:simpleType name="T"><xs:restriction base="xs:string">'
            '<xs:pattern value="[abcd]?{0,5}"/></xs:restriction></xs:simpleType>',
            "meta character",
        ),
        (
            '<xs:simpleType name="T"><xs:restriction base="xs:int">'
            '<xs:minInclusive value="5"/><xs:maxInclusive value="1"/></xs:restriction></xs:simpleType>',
            "",
        ),
    ],
)
def test_facets_xsd_does_not_allow(body: str, expected: str) -> None:
    result = _check(f"<xs:schema {XS}>{body}</xs:schema>")
    assert result.status == "findings"
    assert expected in result.findings[0].message


def test_a_valid_schema_has_no_findings() -> None:
    result = _check(VALID)
    assert result.status == "ok" and result.findings == [] and result.more == 0


def test_an_xsd_11_schema_is_read_as_xsd_11() -> None:
    result = _check(
        f'<xs:schema {XS}><xs:element name="R"><xs:complexType>'
        '<xs:attribute name="a" type="xs:int"/><xs:assert test="@a gt 0"/>'
        "</xs:complexType></xs:element></xs:schema>"
    )
    assert result.status == "ok" and result.version == "1.1"


def test_a_finding_in_an_included_file_names_that_file() -> None:
    main = (
        f'<xs:schema {XS}><xs:include schemaLocation="part.xsd"/>'
        '<xs:element name="R" type="T"/></xs:schema>'
    )
    part = (
        f"<xs:schema {XS}>\n"
        '<xs:simpleType name="T"><xs:restriction base="xs:integer">\n'
        '<xs:fractionDigits value="2"/></xs:restriction></xs:simpleType></xs:schema>'
    )
    model = parse_files_map({"main.xsd": main.encode(), "part.xsd": part.encode()}, "main.xsd")
    result = check_schema(model)
    part_id = next(f.id for f in model.files if f.filename == "part.xsd")
    assert [(f.file_id, f.line) for f in result.findings] == [(part_id, 3)]


def test_a_schema_with_a_missing_file_is_not_checked() -> None:
    result = _check(
        f'<xs:schema {XS}><xs:include schemaLocation="absent.xsd"/>'
        '<xs:element name="R" type="Missing"/></xs:schema>'
    )
    assert result.status == "not_checked" and "absent.xsd" in (result.detail or "")


def test_the_number_of_findings_listed_is_bounded() -> None:
    types = "".join(
        f'<xs:simpleType name="T{i}"><xs:restriction base="xs:integer">'
        '<xs:fractionDigits value="2"/></xs:restriction></xs:simpleType>'
        for i in range(60)
    )
    result = _check(f"<xs:schema {XS}>{types}</xs:schema>")
    assert len(result.findings) == 50 and result.more == 10


class TestEndpoint:
    def _load(self, client: TestClient, text: str) -> str:
        response = client.post("/api/schema/text", json={"filename": "s.xsd", "content": text})
        assert response.status_code == 200, response.text
        return response.json()["schema_id"]

    def test_findings_and_the_cached_answer(self, client: TestClient) -> None:
        schema_id = self._load(client, ILLEGAL_RESTRICTION)
        first = client.get(f"/api/schema/{schema_id}/check")
        assert first.status_code == 200
        assert first.json()["status"] == "findings"
        with patch("app.api.schema.check_schema", side_effect=AssertionError("checked twice")):
            assert client.get(f"/api/schema/{schema_id}/check").json() == first.json()

    def test_a_valid_schema(self, client: TestClient) -> None:
        schema_id = self._load(client, VALID)
        assert client.get(f"/api/schema/{schema_id}/check").json()["status"] == "ok"

    def test_an_unknown_schema(self, client: TestClient) -> None:
        assert client.get("/api/schema/nope/check").status_code == 404


def test_a_very_large_schema_is_left_alone() -> None:
    model = parse_single(VALID.encode(), "s.xsd")
    with patch("app.parser.validation._CHECK_MAX_CHARS", 10):
        result = check_schema(model)
    assert result.status == "not_checked" and "too large" in (result.detail or "")
    assert result.too_large


def test_a_very_large_schema_is_checked_when_asked() -> None:
    model = parse_single(ILLEGAL_RESTRICTION.encode(), "s.xsd")
    with patch("app.parser.validation._CHECK_MAX_CHARS", 10):
        result = check_schema(model, on_demand=True)
    assert result.status == "findings" and not result.too_large


def test_asking_does_not_lift_the_upper_limit() -> None:
    model = parse_single(VALID.encode(), "s.xsd")
    with patch("app.parser.validation._CHECK_ON_DEMAND_MAX_CHARS", 10):
        result = check_schema(model, on_demand=True)
    assert result.status == "not_checked" and not result.too_large


def test_the_api_checks_a_large_schema_on_request(client: TestClient) -> None:
    # A text of its own: the answer for a schema already checked is kept.
    text = VALID.replace("<xs:schema", "<!-- large --><xs:schema", 1)
    loaded = client.post("/api/schema/text", json={"content": text, "filename": "s.xsd"})
    schema_id = loaded.json()["schema_id"]
    with patch("app.parser.validation._CHECK_MAX_CHARS", 10):
        unasked = client.get(f"/api/schema/{schema_id}/check").json()
        asked = client.get(f"/api/schema/{schema_id}/check", params={"large": "true"}).json()
    assert unasked["status"] == "not_checked" and unasked["too_large"]
    assert asked["status"] == "ok" and not asked["too_large"]
