from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_oversized_request_bodies_are_refused_before_any_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    client = TestClient(app)
    body = b"x" * (3 * 1024 * 1024)
    r = client.post("/api/feedback", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert "1 MB" in r.json()["detail"]


def test_bodies_within_the_limit_reach_the_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    r = TestClient(app).post("/api/feedback", content=b"{}", headers={"content-type": "application/json"})
    assert r.status_code == 422
