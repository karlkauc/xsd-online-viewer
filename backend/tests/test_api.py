"""Integration tests for the HTTP API."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser.model import SchemaModel

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestUpload:
    def test_upload_single_xsd(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        response = client.post(
            "/api/schema/upload",
            files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_id"]
        element_names = [e["name"] for e in payload["model"]["elements"]]
        assert "Person" in element_names

    def test_upload_zip(self, client: TestClient) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(FIXTURES / "library.xsd", "library.xsd")
            archive.write(FIXTURES / "types.xsd", "types.xsd")
        response = client.post(
            "/api/schema/upload",
            files={"file": ("bundle.zip", buffer.getvalue(), "application/zip")},
            data={"main_filename": "library.xsd"},
        )
        assert response.status_code == 200, response.text
        files = response.json()["model"]["files"]
        assert {f["filename"] for f in files} == {"library.xsd", "types.xsd"}

    def test_upload_text(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        response = client.post(
            "/api/schema/text",
            json={"filename": "simple.xsd", "content": simple_xsd_bytes.decode("utf-8")},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("declared", ["windows-1251", "ISO-8859-1", "UTF-16"])
    def test_pasted_text_ignores_its_declared_encoding(self, client: TestClient, declared: str) -> None:
        # Pasted text travels as a JSON string and is UTF-8 by the time it is
        # parsed; a declaration copied along with it no longer applies.
        content = (
            f'<?xml version="1.0" encoding="{declared}"?>\n'
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            '<xs:element name="Größe"/><xs:element name="Имя"/></xs:schema>'
        )
        response = client.post("/api/schema/text", json={"filename": "s.xsd", "content": content})
        assert response.status_code == 200, response.text
        model = response.json()["model"]
        assert {e["name"] for e in model["elements"]} == {"Größe", "Имя"}
        assert "Größe" in model["files"][0]["content"]

    def test_formatted_export_of_a_non_utf8_upload(self, client: TestClient) -> None:
        xsd = (
            '<?xml version="1.0" encoding="windows-1251"?>'
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="Имя"/></xs:schema>'
        ).encode("windows-1251")
        loaded = client.post("/api/schema/upload", files={"file": ("s.xsd", xsd, "application/xml")})
        assert loaded.status_code == 200, loaded.text
        body = loaded.json()
        file_id = body["model"]["files"][0]["id"]
        formatted = client.get(f"/api/schema/{body['schema_id']}/file/{file_id}/formatted")
        assert formatted.status_code == 200, formatted.text
        assert "Имя" in formatted.text

    def test_model_validation_error_is_not_shown_raw(self, client: TestClient) -> None:
        # A value the model has no room for must not surface as pydantic's
        # "1 validation error for SchemaModel … [type=literal_error, …]".
        with patch(
            "app.api.schema.parse_with_url_fallback",
            side_effect=lambda *a, **k: SchemaModel(schema_id="x", element_form_default="odd"),
        ):
            response = client.post("/api/schema/text", json={"filename": "s.xsd", "content": "<x/>"})
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "'odd'" in detail and "element_form_default" in detail
        assert "validation error for" not in detail and "type=" not in detail

    def test_upload_dtd_rejected(self, client: TestClient, xxe_attack_bytes: bytes) -> None:
        response = client.post(
            "/api/schema/upload",
            files={"file": ("xxe.xsd", xxe_attack_bytes, "application/xml")},
        )
        assert response.status_code == 400

    def test_cache_retrieval(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        first = client.post(
            "/api/schema/upload",
            files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
        )
        schema_id = first.json()["schema_id"]
        again = client.get(f"/api/schema/{schema_id}")
        assert again.status_code == 200
        assert again.json()["schema_id"] == schema_id

    def test_missing_schema_404(self, client: TestClient) -> None:
        response = client.get("/api/schema/does-not-exist")
        assert response.status_code == 404


class TestHealth:
    def test_health_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestExport:
    def test_html_export(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
        )
        schema_id = upload.json()["schema_id"]
        response = client.get(f"/api/schema/{schema_id}/export/html")
        assert response.status_code == 200
        assert "PersonType" in response.text
        assert response.headers["content-type"].startswith("text/html")

    def test_formatted_file_download(
        self, client: TestClient, simple_xsd_bytes: bytes
    ) -> None:
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
        )
        model = upload.json()["model"]
        schema_id = upload.json()["schema_id"]
        file_id = model["files"][0]["id"]
        response = client.get(f"/api/schema/{schema_id}/file/{file_id}/formatted")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")
        assert "<?xml" in response.text


class TestMultiFileUpload:
    def test_two_loose_files_resolve_each_other(self, client: TestClient) -> None:
        response = client.post(
            "/api/schema/upload",
            files=[
                ("file", ("types.xsd", (FIXTURES / "types.xsd").read_bytes(), "application/xml")),
                ("file", ("library.xsd", (FIXTURES / "library.xsd").read_bytes(), "application/xml")),
            ],
        )
        assert response.status_code == 200, response.text
        model = response.json()["model"]
        assert {f["filename"] for f in model["files"]} == {"library.xsd", "types.xsd"}
        assert not [d for d in model["diagnostics"] if d["severity"] == "error"]

    def test_explicit_main_wins(self, client: TestClient) -> None:
        response = client.post(
            "/api/schema/upload",
            files=[
                ("file", ("a.xsd", (FIXTURES / "types.xsd").read_bytes(), "application/xml")),
                ("file", ("library.xsd", (FIXTURES / "library.xsd").read_bytes(), "application/xml")),
            ],
            data={"main_filename": "library.xsd"},
        )
        assert response.status_code == 200, response.text
        main = [f for f in response.json()["model"]["files"] if f["relationship"] == "main"]
        assert [f["filename"] for f in main] == ["library.xsd"]

    def test_wrong_main_lists_the_candidates(self, client: TestClient) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(FIXTURES / "library.xsd", "schemas/library.xsd")
            archive.write(FIXTURES / "types.xsd", "schemas/types.xsd")
        response = client.post(
            "/api/schema/upload",
            files={"file": ("bundle.zip", buffer.getvalue(), "application/zip")},
            data={"main_filename": "library.xsd"},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail.startswith("main schema 'library.xsd' is not among the uploaded files")
        assert "schemas/library.xsd" in detail and "schemas/types.xsd" in detail


class TestSampleXml:
    def test_sample_for_root_element(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
        )
        schema_id = upload.json()["schema_id"]
        response = client.get(
            f"/api/schema/{schema_id}/sample",
            params={"element": "element:{http://example.com/simple}Person"},
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/xml")
        assert 'filename="Person-sample.xml"' in response.headers["content-disposition"]
        body = response.text
        assert "<tns:FirstName>Max</tns:FirstName>" in body
        assert 'xmlns:tns="http://example.com/simple"' in body
        assert "<tns:Age>" not in body

        with_optional = client.get(
            f"/api/schema/{schema_id}/sample",
            params={"element": "element:{http://example.com/simple}Person", "optional": "true"},
        )
        assert "<tns:Age>0</tns:Age>" in with_optional.text
        assert "x-sample-missing" not in with_optional.headers

    def test_incomplete_schema_names_its_missing_references(self, client: TestClient) -> None:
        """Such a schema cannot compile, so the dialog skips its check (SampleXmlDialog).

        Names travel percent-encoded: a header is latin-1, a QName need not be.
        """
        import json
        from urllib.parse import unquote

        xsd = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:doc" xmlns:cac="urn:cac">
  <xs:import namespace="urn:cac" schemaLocation="missing.xsd"/>
  <xs:element name="Invoice"><xs:complexType><xs:sequence>
    <xs:element ref="cac:Party"/>
    <xs:element name="Total" type="cac:Сумма"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>""".encode()
        upload = client.post(
            "/api/schema/upload", files={"file": ("invoice.xsd", xsd, "application/xml")}
        )
        schema_id = upload.json()["schema_id"]
        response = client.get(
            f"/api/schema/{schema_id}/sample", params={"element": "element:{urn:doc}Invoice"}
        )
        assert response.status_code == 200, response.text
        assert json.loads(unquote(response.headers["x-sample-missing"])) == {
            "count": 2,
            "names": ["cac:Party", "cac:Сумма"],
        }
        assert "X-Sample-Missing" in response.headers["access-control-expose-headers"]

    def test_unknown_element_or_schema_404(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")},
        )
        schema_id = upload.json()["schema_id"]
        missing = client.get(f"/api/schema/{schema_id}/sample", params={"element": "element:Nope"})
        assert missing.status_code == 404
        expired = client.get("/api/schema/expired/sample", params={"element": "x"})
        assert expired.status_code == 404


class TestBundleExport:
    def test_single_file_comes_back_as_xsd(self, client: TestClient, simple_xsd_bytes: bytes) -> None:
        upload = client.post(
            "/api/schema/upload", files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")}
        )
        schema_id = upload.json()["schema_id"]
        response = client.get(f"/api/schema/{schema_id}/export/bundle")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")
        assert 'filename="simple.xsd"' in response.headers["content-disposition"]
        assert response.headers["x-main-filename"] == "simple.xsd"
        assert response.content == simple_xsd_bytes

    def test_multi_file_comes_back_as_zip(self, client: TestClient) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(FIXTURES / "library.xsd", "schemas/library.xsd")
            archive.write(FIXTURES / "types.xsd", "schemas/types.xsd")
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("bundle.zip", buffer.getvalue(), "application/zip")},
            data={"main_filename": "schemas/library.xsd"},
        )
        schema_id = upload.json()["schema_id"]
        response = client.get(f"/api/schema/{schema_id}/export/bundle")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert 'filename="library-bundle.zip"' in response.headers["content-disposition"]
        assert response.headers["x-main-filename"] == "schemas/library.xsd"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert sorted(archive.namelist()) == ["schemas/library.xsd", "schemas/types.xsd"]
            assert archive.read("schemas/types.xsd") == (FIXTURES / "types.xsd").read_bytes()

    def test_expired_schema_404(self, client: TestClient) -> None:
        assert client.get("/api/schema/nope/export/bundle").status_code == 404
