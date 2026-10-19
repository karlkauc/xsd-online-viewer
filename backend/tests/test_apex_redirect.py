"""Bare domain → canonical www origin (app/main.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _client(host: str) -> TestClient:
    return TestClient(app, base_url=f"https://{host}", follow_redirects=False)


def test_apex_page_load_is_permanently_redirected_with_path_and_query() -> None:
    response = _client("xsd-viewer.online").get("/about", params={"x": "1"})
    assert response.status_code == 301
    assert response.headers["location"] == "https://www.xsd-viewer.online/about?x=1"


def test_apex_post_keeps_its_method() -> None:
    response = _client("xsd-viewer.online").post("/api/feedback", json={})
    assert response.status_code == 308
    assert response.headers["location"] == "https://www.xsd-viewer.online/api/feedback"


def test_www_and_other_hosts_are_served() -> None:
    assert _client("www.xsd-viewer.online").get("/api/health").status_code == 200
    assert _client("service-1.europe-west1.run.app").get("/api/health").status_code == 200
