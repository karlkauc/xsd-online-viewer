"""URL normalisation and HTML-response detection (app/parser/urls.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser.urls import html_response_message, looks_like_html, normalize_schema_url


@pytest.mark.parametrize(
    ("pasted", "expected"),
    [
        (
            "https://github.com/fundsxml/schema/blob/master/FundsXML4.xsd",
            "https://raw.githubusercontent.com/fundsxml/schema/master/FundsXML4.xsd",
        ),
        (
            "https://github.com/ept/oaccounts/blob/master/xsd/common/UBL-CommonAggregateComponents-2.0.xsd?plain=1",
            "https://raw.githubusercontent.com/ept/oaccounts/master/xsd/common/UBL-CommonAggregateComponents-2.0.xsd",
        ),
        (
            "https://github.com/gbif/eml-profile/raw/master/eml-gbif-profile.xsd",
            "https://raw.githubusercontent.com/gbif/eml-profile/master/eml-gbif-profile.xsd",
        ),
        (
            "https://gitlab.com/group/sub/project/-/blob/main/schemas/a.xsd",
            "https://gitlab.com/group/sub/project/-/raw/main/schemas/a.xsd",
        ),
        (
            "https://bitbucket.org/ws/repo/src/main/x.xsd",
            "https://bitbucket.org/ws/repo/raw/main/x.xsd",
        ),
    ],
)
def test_browse_urls_are_rewritten_to_raw(pasted: str, expected: str) -> None:
    assert normalize_schema_url(pasted) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://raw.githubusercontent.com/fundsxml/schema/master/FundsXML4.xsd",
        "https://github.com/fundsxml/schema/releases",
        "https://github.com/fundsxml/schema",
        "https://inspire.ec.europa.eu/schemas/ad/4.0/Addresses.xsd",
        "http://example.com/blob/x.xsd",
        "not a url",
    ],
)
def test_other_urls_are_untouched(url: str) -> None:
    assert normalize_schema_url(url) == url


def test_html_detected_by_content_type() -> None:
    assert looks_like_html(b"<?xml version='1.0'?><x/>", "text/html; charset=utf-8")
    assert not looks_like_html(b"<?xml version='1.0'?><x/>", "application/xml")
    assert not looks_like_html(b"<?xml version='1.0'?><x/>", None)


def test_html_detected_by_body() -> None:
    assert looks_like_html(b"\n<!DOCTYPE html>\n<html lang=en>", "application/octet-stream")
    assert looks_like_html(b"\xef\xbb\xbf<html>", None)
    assert not looks_like_html(b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>", None)


def test_message_points_at_the_raw_button() -> None:
    msg = html_response_message("https://example.com/x")
    assert msg.startswith("https://example.com/x returned a web page")
    assert "'Raw'" in msg


def test_url_endpoint_rejects_html_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.parser.security import FetchedResource

    client = TestClient(app)

    def fake_fetch(url: str) -> FetchedResource:
        return FetchedResource(
            url=url, content=b"<!DOCTYPE html><html><body>GitHub</body></html>", content_type="text/html"
        )

    monkeypatch.setattr("app.api.schema.fetch_schema_url", fake_fetch)
    response = client.post("/api/schema/url", json={"url": "https://example.com/page"})
    assert response.status_code == 400
    assert "returned a web page" in response.json()["detail"]
    assert "'Raw'" in response.json()["detail"]


def test_fetch_normalises_github_blob_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.parser import security

    seen: list[str] = []

    def fake_verify(url: str) -> None:
        seen.append(url)
        raise security.SecurityError("stop here")

    monkeypatch.setattr(security, "_verify_url", fake_verify)
    with pytest.raises(security.SecurityError):
        security.fetch_schema_url("https://github.com/o/r/blob/main/a.xsd")
    assert seen == ["https://raw.githubusercontent.com/o/r/main/a.xsd"]
