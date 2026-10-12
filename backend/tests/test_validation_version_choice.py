"""Validating as the XSD version the caller names (``?xsd_version=``).

Nothing in these schemas is XSD 1.1 syntax, so they are detected as 1.0 —
and yet the two versions disagree about the documents.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser.validation import ValidationSetupError, validate_xml
from app.parser.xsd_parser import parse_single

pytest.importorskip("xmlschema")

XS = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
# XSD 1.0 orders 2000+11:00 before 2000+13:00 by the time zone alone; XSD 1.1
# compares the moments the years begin at.
YEARS = f"""<xs:schema {XS}>
  <xs:element name="y"><xs:simpleType><xs:restriction base="xs:gYear">
    <xs:minInclusive value="2000+13:00"/>
  </xs:restriction></xs:simpleType></xs:element>
</xs:schema>"""
YEAR = b"<y>2000+11:00</y>"
# Valid XSD 1.1 only: an element with two attributes of type ID.
TWO_IDS = f"""<xs:schema {XS}>
  <xs:element name="e"><xs:complexType>
    <xs:attribute name="a" type="xs:ID"/><xs:attribute name="b" type="xs:ID"/>
  </xs:complexType></xs:element>
</xs:schema>"""
ASSERTED = f"""<xs:schema {XS}>
  <xs:element name="n"><xs:complexType>
    <xs:attribute name="v" type="xs:int"/><xs:assert test="@v gt 1"/>
  </xs:complexType></xs:element>
</xs:schema>"""


def test_the_schema_decides_when_nobody_says() -> None:
    model = parse_single(YEARS.encode(), "s.xsd")
    assert model.xsd_version == "1.0"
    result = validate_xml(model, YEAR)
    assert result.validator == "libxml2" and not result.is_valid


def test_the_same_document_as_xsd_1_1() -> None:
    result = validate_xml(parse_single(YEARS.encode(), "s.xsd"), YEAR, version="1.1")
    assert result.validator == "xmlschema" and result.is_valid


def test_xsd_1_0_for_a_schema_detected_as_1_1_is_not_quietly_something_else() -> None:
    model = parse_single(ASSERTED.encode(), "s.xsd")
    assert model.xsd_version == "1.1"
    assert validate_xml(model, b'<n v="1"/>').validator == "xmlschema"
    with pytest.raises(ValidationSetupError, match="read as XSD 1.0, the schema is not valid"):
        validate_xml(model, b'<n v="1"/>', version="1.0")


def test_a_schema_only_xsd_1_1_allows() -> None:
    model = parse_single(TWO_IDS.encode(), "s.xsd")
    result = validate_xml(model, b'<e a="x" b="y"/>', version="1.1")
    assert result.validator == "xmlschema" and result.is_valid


class TestEndpoints:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    @pytest.fixture
    def schema_id(self, client: TestClient) -> str:
        loaded = client.post("/api/schema/text", json={"content": YEARS, "filename": "s.xsd"})
        return loaded.json()["schema_id"]

    def test_text(self, client: TestClient, schema_id: str) -> None:
        url = f"/api/schema/{schema_id}/validate/text"
        body = {"content": YEAR.decode(), "filename": "d.xml"}
        assert client.post(url, json=body).json()["is_valid"] is False
        assert client.post(url, json=body, params={"xsd_version": "1.0"}).json()["is_valid"] is False
        chosen = client.post(url, json=body, params={"xsd_version": "1.1"}).json()
        assert chosen["is_valid"] is True and chosen["validator"] == "xmlschema"

    def test_upload(self, client: TestClient, schema_id: str) -> None:
        chosen = client.post(
            f"/api/schema/{schema_id}/validate/upload",
            files={"file": ("d.xml", YEAR, "application/xml")},
            params={"xsd_version": "1.1"},
        )
        assert chosen.json()["is_valid"] is True

    def test_a_version_there_is_not(self, client: TestClient, schema_id: str) -> None:
        answer = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": YEAR.decode(), "filename": "d.xml"},
            params={"xsd_version": "2.0"},
        )
        assert answer.status_code == 422
