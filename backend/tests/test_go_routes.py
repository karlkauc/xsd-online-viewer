"""Counted outbound redirects (app/api/go.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def test_default_goes_to_the_docs_site() -> None:
    response = _client().get("/go/freexmltoolkit")
    assert response.status_code == 302
    assert response.headers["location"] == "https://karlkauc.github.io/FreeXmlToolkit/"


def test_releases_target_and_unknown_fallback() -> None:
    client = _client()
    assert (
        client.get("/go/freexmltoolkit", params={"to": "releases"}).headers["location"]
        == "https://github.com/karlkauc/FreeXmlToolkit/releases"
    )
    assert (
        client.get("/go/freexmltoolkit", params={"to": "https://evil.example"}).headers["location"]
        == "https://karlkauc.github.io/FreeXmlToolkit/"
    )


def test_other_go_paths_are_404() -> None:
    assert _client().get("/go/unknown").status_code == 404
