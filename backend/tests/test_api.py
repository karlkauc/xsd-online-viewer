"""Integration tests for the HTTP API."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

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
        assert "<tns:FirstName>string</tns:FirstName>" in body
        assert 'xmlns:tns="http://example.com/simple"' in body
        assert "<tns:Age>" not in body

        with_optional = client.get(
            f"/api/schema/{schema_id}/sample",
            params={"element": "element:{http://example.com/simple}Person", "optional": "true"},
        )
        assert "<tns:Age>0</tns:Age>" in with_optional.text

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
