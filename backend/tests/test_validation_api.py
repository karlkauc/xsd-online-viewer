"""Integration tests for XML-against-XSD validation."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser.security import FetchedResource

FIXTURES = Path(__file__).parent / "fixtures"

VALID_PERSON = (
    '<Person xmlns="http://example.com/simple" id="p1">'
    "<FirstName>Ada</FirstName><LastName>Lovelace</LastName>"
    "<Age>36</Age></Person>"
)
INVALID_PERSON = (
    '<Person xmlns="http://example.com/simple" id="p1">'
    "<FirstName>Ada</FirstName><LastName>Lovelace</LastName>"
    "<Age>200</Age></Person>"
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _upload_simple(client: TestClient, simple_xsd_bytes: bytes) -> str:
    response = client.post(
        "/api/schema/upload",
        files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
    )
    assert response.status_code == 200, response.text
    return response.json()["schema_id"]


class TestValidation:
    def test_valid_document(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)
        response = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": VALID_PERSON},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["errors"] == []
        assert body["reformatted_xml"] is not None
        # pretty-printed: multi-line with an XML declaration
        assert body["reformatted_xml"].startswith("<?xml")
        assert "\n" in body["reformatted_xml"]

    def test_invalid_document_reports_error_with_xsd_ref(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)
        response = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": INVALID_PERSON},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert len(body["errors"]) >= 1
        err = body["errors"][0]
        assert err["kind"] == "schema-validation"
        assert err["line"] and err["line"] >= 1
        assert err["type_name"]
        # best-effort mapping: the offending <Age> element resolves to a decl
        assert err["xsd_ref"] is not None
        assert err["xsd_ref"]["id"]

    def test_single_line_input_error_line_refers_to_reformatted_text(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)
        # whole document on one physical line
        response = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": INVALID_PERSON},
        )
        body = response.json()
        # after reformatting the <Age> error lands well past line 1
        assert body["errors"][0]["line"] > 1

    def test_not_well_formed(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)
        response = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": "<Person><FirstName></Person>"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["reformatted_xml"] is None
        assert len(body["errors"]) == 1
        assert body["errors"][0]["kind"] == "not-well-formed"
        assert body["errors"][0]["severity"] == "fatal"
        assert body["errors"][0]["line"]

    def test_multiple_errors_order_preserved(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)
        # missing required FirstName/LastName and Age out of range
        doc = (
            '<Person xmlns="http://example.com/simple" id="p1">'
            "<Age>200</Age></Person>"
        )
        response = client.post(
            f"/api/schema/{schema_id}/validate/text", json={"content": doc}
        )
        body = response.json()
        assert body["is_valid"] is False
        assert len(body["errors"]) >= 1
        lines = [e["line"] for e in body["errors"] if e["line"]]
        assert lines == sorted(lines)  # libxml2 document-order, not re-sorted

    def test_cache_miss_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/schema/deadbeef/validate/text", json={"content": VALID_PERSON}
        )
        assert response.status_code == 404

    def test_size_cap_413(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        from app.config import settings

        schema_id = _upload_simple(client, simple_xsd_bytes)
        huge = "<a>" + "x" * (settings.max_upload_bytes + 1) + "</a>"
        response = client.post(
            f"/api/schema/{schema_id}/validate/text", json={"content": huge}
        )
        assert response.status_code == 413

    def test_upload_variant(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)
        response = client.post(
            f"/api/schema/{schema_id}/validate/upload",
            files={"file": ("doc.xml", VALID_PERSON.encode(), "application/xml")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True

    def test_url_variant(
        self,
        client: TestClient,
        simple_xsd_bytes: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        schema_id = _upload_simple(client, simple_xsd_bytes)

        def fake_fetch(url: str) -> FetchedResource:
            return FetchedResource(
                url=url, content=VALID_PERSON.encode(), content_type="application/xml"
            )

        monkeypatch.setattr("app.api.schema.fetch_schema_url", fake_fetch)
        response = client.post(
            f"/api/schema/{schema_id}/validate/url",
            json={"url": "https://example.com/doc.xml"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True

    def test_url_variant_ssrf_rejected(
        self,
        client: TestClient,
        simple_xsd_bytes: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.parser.security import SecurityError

        schema_id = _upload_simple(client, simple_xsd_bytes)

        def fake_fetch(url: str) -> FetchedResource:
            raise SecurityError("blocked private address")

        monkeypatch.setattr("app.api.schema.fetch_schema_url", fake_fetch)
        response = client.post(
            f"/api/schema/{schema_id}/validate/url",
            json={"url": "http://localhost/secret"},
        )
        assert response.status_code == 400

    def test_multi_file_schema_resolves_include(self, client: TestClient) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(FIXTURES / "library.xsd", "library.xsd")
            archive.write(FIXTURES / "types.xsd", "types.xsd")
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("bundle.zip", buffer.getvalue(), "application/zip")},
            data={"main_filename": "library.xsd"},
        )
        assert upload.status_code == 200, upload.text
        schema_id = upload.json()["schema_id"]

        # ISBN obeys the pattern declared in the *included* types.xsd
        doc = (
            '<Library xmlns="http://example.com/library">'
            "<Book><Title>T</Title><Author>A</Author>"
            "<ISBN>123-1234567890</ISBN></Book></Library>"
        )
        response = client.post(
            f"/api/schema/{schema_id}/validate/text", json={"content": doc}
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True

        bad = doc.replace("123-1234567890", "not-an-isbn")
        bad_resp = client.post(
            f"/api/schema/{schema_id}/validate/text", json={"content": bad}
        )
        assert bad_resp.json()["is_valid"] is False
