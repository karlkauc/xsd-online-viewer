"""Tests for the FundsXML releases endpoint."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import releases as releases_module
from app.main import app


@pytest.fixture(autouse=True)
def _clear_releases_cache() -> None:
    releases_module._reset_cache_for_tests()
    yield
    releases_module._reset_cache_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _github_payload() -> list[dict[str, Any]]:
    return [
        {
            "tag_name": "4.2.10",
            "name": "4.2.10",
            "published_at": "2026-01-23T15:39:25Z",
            "prerelease": False,
            "draft": False,
            "html_url": "https://github.com/fundsxml/schema/releases/tag/4.2.10",
            "assets": [
                {
                    "name": "FundsXML.xsd",
                    "browser_download_url": (
                        "https://github.com/fundsxml/schema/releases/download/4.2.10/FundsXML.xsd"
                    ),
                    "content_type": "text/xml",
                    "size": 2565081,
                },
                {
                    "name": "CHANGELOG.md",
                    "browser_download_url": (
                        "https://github.com/fundsxml/schema/releases/download/4.2.10/CHANGELOG.md"
                    ),
                    "content_type": "text/markdown",
                    "size": 1234,
                },
            ],
        },
        {
            "tag_name": "4.2.9-rc1",
            "name": "4.2.9 Release Candidate",
            "published_at": "2025-12-01T09:00:00Z",
            "prerelease": True,
            "draft": False,
            "html_url": "https://github.com/fundsxml/schema/releases/tag/4.2.9-rc1",
            "assets": [
                {
                    "name": "FundsXML.xsd",
                    "browser_download_url": (
                        "https://github.com/fundsxml/schema/releases/download/"
                        "4.2.9-rc1/FundsXML.xsd"
                    ),
                    "content_type": "text/xml",
                    "size": 2500000,
                }
            ],
        },
        {
            "tag_name": "4.2.8-draft",
            "name": "Draft",
            "published_at": "2025-11-01T09:00:00Z",
            "prerelease": False,
            "draft": True,
            "html_url": "https://github.com/fundsxml/schema/releases/tag/4.2.8-draft",
            "assets": [
                {
                    "name": "FundsXML.xsd",
                    "browser_download_url": "https://example.invalid/draft.xsd",
                    "content_type": "text/xml",
                    "size": 1,
                }
            ],
        },
        {
            "tag_name": "4.2.7-notes-only",
            "name": "Notes Only",
            "published_at": "2025-10-01T09:00:00Z",
            "prerelease": False,
            "draft": False,
            "html_url": "https://github.com/fundsxml/schema/releases/tag/4.2.7-notes-only",
            "assets": [
                {
                    "name": "RELEASE_NOTES.md",
                    "browser_download_url": (
                        "https://github.com/fundsxml/schema/releases/download/"
                        "4.2.7-notes-only/RELEASE_NOTES.md"
                    ),
                    "content_type": "text/markdown",
                    "size": 500,
                }
            ],
        },
    ]


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_body: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_body
        self.text = text or ("" if json_body is None else "<json>")
        self.headers = headers or {}
        if json_body is None:
            self.content = self.text.encode("utf-8")
        else:
            import json as _json

            self.content = _json.dumps(json_body).encode("utf-8")

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeAsyncClient:
    """Replacement for httpx.AsyncClient used to drive the tests."""

    _factory = None  # set by install()
    calls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        FakeAsyncClient.calls.append(url)
        assert FakeAsyncClient._factory is not None, "no FakeAsyncClient factory installed"
        return FakeAsyncClient._factory()


def _install_fake(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    FakeAsyncClient._factory = factory
    FakeAsyncClient.calls = []
    monkeypatch.setattr(releases_module.httpx, "AsyncClient", FakeAsyncClient)


class TestReleasesEndpoint:
    def test_returns_shaped_releases(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, lambda: FakeResponse(200, json_body=_github_payload()))
        response = client.get("/api/fundsxml/releases")
        assert response.status_code == 200, response.text
        body = response.json()
        tags = [r["tag_name"] for r in body["releases"]]
        assert tags == ["4.2.10", "4.2.9-rc1"]

    def test_filters_non_xsd_and_drops_empty(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, lambda: FakeResponse(200, json_body=_github_payload()))
        response = client.get("/api/fundsxml/releases")
        assert response.status_code == 200
        body = response.json()
        tags = {r["tag_name"] for r in body["releases"]}
        assert "4.2.8-draft" not in tags, "draft must be filtered"
        assert "4.2.7-notes-only" not in tags, "release without XSD must be filtered"
        first = next(r for r in body["releases"] if r["tag_name"] == "4.2.10")
        assert [a["filename"] for a in first["assets"]] == ["FundsXML.xsd"]

    def test_prerelease_flag_preserved(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, lambda: FakeResponse(200, json_body=_github_payload()))
        response = client.get("/api/fundsxml/releases")
        by_tag = {r["tag_name"]: r for r in response.json()["releases"]}
        assert by_tag["4.2.10"]["prerelease"] is False
        assert by_tag["4.2.9-rc1"]["prerelease"] is True

    def test_cache_hit_skips_second_fetch(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, lambda: FakeResponse(200, json_body=_github_payload()))
        r1 = client.get("/api/fundsxml/releases")
        r2 = client.get("/api/fundsxml/releases")
        assert r1.status_code == 200 and r2.status_code == 200
        assert len(FakeAsyncClient.calls) == 1
        assert r1.json()["cached_at"] == r2.json()["cached_at"]

    def test_rate_limit_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(
            monkeypatch,
            lambda: FakeResponse(
                403,
                text="API rate limit exceeded for user",
                headers={"X-RateLimit-Reset": "120"},
            ),
        )
        response = client.get("/api/fundsxml/releases")
        assert response.status_code == 503
        assert response.headers.get("Retry-After") == "120"

    def test_upstream_5xx_returns_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, lambda: FakeResponse(500, text="boom"))
        response = client.get("/api/fundsxml/releases")
        assert response.status_code == 502

    def test_network_error_returns_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom() -> FakeResponse:
            raise httpx.ConnectError("dns fail")

        _install_fake(monkeypatch, boom)
        response = client.get("/api/fundsxml/releases")
        assert response.status_code == 502

    def test_stale_cache_served_on_upstream_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(monkeypatch, lambda: FakeResponse(200, json_body=_github_payload()))
        ok = client.get("/api/fundsxml/releases")
        assert ok.status_code == 200

        # Force TTL expiry so the next request hits the upstream path.
        releases_module._cached_at_monotonic = 0.0

        def boom() -> FakeResponse:
            raise httpx.ConnectError("dns fail")

        _install_fake(monkeypatch, boom)
        stale = client.get("/api/fundsxml/releases")
        assert stale.status_code == 200
        assert stale.json()["releases"] == ok.json()["releases"]


LIBRARY_MAIN_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:lib="http://example.com/library"
           targetNamespace="http://example.com/library"
           elementFormDefault="qualified">
  <xs:import namespace="http://example.com/signatures"
             schemaLocation="signatures.xsd"/>
  <xs:element name="Library">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Book" maxOccurs="unbounded">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="Title" type="xs:string"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

SIGNATURES_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:sig="http://example.com/signatures"
           targetNamespace="http://example.com/signatures"
           elementFormDefault="qualified">
  <xs:simpleType name="SignatureValue">
    <xs:restriction base="xs:base64Binary"/>
  </xs:simpleType>
</xs:schema>
"""


def _multi_asset_payload() -> list[dict[str, Any]]:
    """A release with two sibling XSD assets — mirrors FundsXML.xsd +
    xmldsig-core-schema.xsd."""
    return [
        {
            "tag_name": "1.0.0",
            "name": "1.0.0",
            "published_at": "2026-04-01T00:00:00Z",
            "prerelease": False,
            "draft": False,
            "html_url": "https://github.com/example/schema/releases/tag/1.0.0",
            "assets": [
                {
                    "name": "Library.xsd",
                    "browser_download_url": "https://example.test/Library.xsd",
                    "content_type": "text/xml",
                    "size": len(LIBRARY_MAIN_XSD),
                },
                {
                    "name": "signatures.xsd",
                    "browser_download_url": "https://example.test/signatures.xsd",
                    "content_type": "text/xml",
                    "size": len(SIGNATURES_XSD),
                },
            ],
        }
    ]


class _FakeFetched:
    def __init__(self, url: str, content: bytes) -> None:
        self.url = url
        self.content = content
        self.content_type = "text/xml"


def _install_fake_asset_fetcher(
    monkeypatch: pytest.MonkeyPatch, files: dict[str, bytes]
) -> list[str]:
    """Replace fetch_schema_url in the releases module so asset downloads
    come from the in-memory ``files`` mapping keyed by download URL."""
    calls: list[str] = []

    def _fake(url: str) -> _FakeFetched:
        calls.append(url)
        if url not in files:
            raise AssertionError(f"unexpected asset fetch: {url!r}")
        return _FakeFetched(url=url, content=files[url])

    monkeypatch.setattr(releases_module, "fetch_schema_url", _fake)
    return calls


class TestLoadReleaseEndpoint:
    def test_loads_multi_asset_release(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(
            monkeypatch, lambda: FakeResponse(200, json_body=_multi_asset_payload())
        )
        fetched = _install_fake_asset_fetcher(
            monkeypatch,
            {
                "https://example.test/Library.xsd": LIBRARY_MAIN_XSD,
                "https://example.test/signatures.xsd": SIGNATURES_XSD,
            },
        )

        response = client.post(
            "/api/fundsxml/releases/1.0.0/load",
            json={"main_filename": "Library.xsd"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        # Both files are in the parsed schema and the import resolved.
        filenames = {f["filename"] for f in body["model"]["files"]}
        assert filenames == {"Library.xsd", "signatures.xsd"}
        # No unresolved-reference warnings from the sibling XSD.
        diagnostic_messages = [d["message"] for d in body["model"]["diagnostics"]]
        assert not any(
            "signatures.xsd" in msg and "unresolved" in msg
            for msg in diagnostic_messages
        ), diagnostic_messages
        # Both assets were fetched.
        assert sorted(fetched) == [
            "https://example.test/Library.xsd",
            "https://example.test/signatures.xsd",
        ]

    def test_unknown_tag_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(
            monkeypatch, lambda: FakeResponse(200, json_body=_multi_asset_payload())
        )
        response = client.post(
            "/api/fundsxml/releases/nope/load",
            json={"main_filename": "Library.xsd"},
        )
        assert response.status_code == 404
        assert "'nope'" in response.json()["detail"]

    def test_unknown_main_filename_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake(
            monkeypatch, lambda: FakeResponse(200, json_body=_multi_asset_payload())
        )
        response = client.post(
            "/api/fundsxml/releases/1.0.0/load",
            json={"main_filename": "missing.xsd"},
        )
        assert response.status_code == 404
        assert "missing.xsd" in response.json()["detail"]
