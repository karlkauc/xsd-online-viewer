"""End-to-end: events reach the recorder through middleware + routers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.usage.context import UsageTracker
from app.usage.events import UsageEvent
from app.usage.recorder import UsageRecorder


class ListRecorder(UsageRecorder):
    def __init__(self) -> None:
        super().__init__("postgresql://fake")
        self.events: list[UsageEvent] = []
        self.drains = 0

    def record(self, event: UsageEvent) -> bool:
        self.events.append(event)
        return True

    async def drain(self, timeout: float = 2.0) -> bool:
        self.drains += 1
        return True


@pytest.fixture
def recorder() -> Iterator[ListRecorder]:
    rec = ListRecorder()
    app.state.usage = UsageTracker(rec, geoip=None, hash_secret="test")
    try:
        yield rec
    finally:
        del app.state.usage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={"user-agent": "pytest-browser", "referer": "https://ref.example/p?x=1"})


def test_upload_ok(client: TestClient, recorder: ListRecorder, simple_xsd_bytes: bytes) -> None:
    files = {"file": ("dir/simple.xsd", simple_xsd_bytes, "application/xml")}
    r = client.post("/api/schema/upload", files=files)
    assert r.status_code == 200
    (ev,) = recorder.events
    assert ev.event_type == "schema_load" and ev.source == "upload" and ev.status == "ok"
    assert ev.schema_name == "simple.xsd"
    assert ev.input_bytes == len(simple_xsd_bytes)
    assert ev.element_count and ev.file_count == 1 and ev.duration_ms is not None
    assert ev.visitor_hash and ev.user_agent == "pytest-browser" and ev.device == "desktop"
    assert ev.referrer == "https://ref.example/p"
    assert recorder.drains == 1


def test_upload_parse_error(client: TestClient, recorder: ListRecorder, xxe_attack_bytes: bytes) -> None:
    r = client.post("/api/schema/upload", files={"file": ("xxe.xsd", xxe_attack_bytes, "application/xml")})
    assert r.status_code == 400
    (ev,) = recorder.events
    assert ev.status == "parse_error" and ev.status_code == 400 and ev.error_detail


def test_text_and_validate_and_export(
    client: TestClient, recorder: ListRecorder, simple_xsd_bytes: bytes
) -> None:
    r = client.post("/api/schema/text", json={"filename": "s.xsd", "content": simple_xsd_bytes.decode()})
    schema_id = r.json()["schema_id"]
    client.post(f"/api/schema/{schema_id}/validate/text", json={"content": "<Nope/>"})
    client.get(f"/api/schema/{schema_id}/export/html")
    client.get("/api/schema/nope/export/html")
    kinds = [(e.event_type, e.source, e.status) for e in recorder.events]
    assert kinds == [
        ("schema_load", "text", "ok"),
        ("validate", "text", "invalid"),
        ("export", "html", "ok"),
        ("export", "html", "rejected"),
    ]
    assert recorder.events[1].error_count and recorder.events[1].error_count > 0


def test_sample_xml_is_recorded(
    client: TestClient, recorder: ListRecorder, simple_xsd_bytes: bytes
) -> None:
    r = client.post("/api/schema/text", json={"filename": "s.xsd", "content": simple_xsd_bytes.decode()})
    schema_id = r.json()["schema_id"]
    ok = client.get(
        f"/api/schema/{schema_id}/sample",
        params={"element": "element:{http://example.com/simple}Person", "optional": "true"},
    )
    assert ok.status_code == 200
    client.get(f"/api/schema/{schema_id}/sample", params={"element": "element:Nope"})
    _, sample_ok, sample_missing = recorder.events
    assert (sample_ok.event_type, sample_ok.source, sample_ok.status) == ("export", "sample", "ok")
    assert sample_ok.schema_name == "s.xsd"
    assert sample_ok.target_namespace == "http://example.com/simple"
    assert sample_ok.input_bytes == len(ok.content)
    assert sample_ok.duration_ms is not None
    assert (sample_missing.status, sample_missing.status_code) == ("rejected", 404)
    assert sample_missing.error_detail == "element not found: element:Nope"


def test_outbound_click_is_recorded_as_page_view(client: TestClient, recorder: ListRecorder) -> None:
    r = client.get("/go/freexmltoolkit", params={"to": "releases"}, follow_redirects=False)
    assert r.status_code == 302
    (ev,) = recorder.events
    assert (ev.event_type, ev.path, ev.source, ev.status_code) == (
        "page_view", "/go/freexmltoolkit/releases", "freexmltoolkit", 302,
    )


def test_url_rejected(client: TestClient, recorder: ListRecorder) -> None:
    r = client.post("/api/schema/url", json={"url": "http://127.0.0.1/x.xsd?secret=1"})
    assert r.status_code == 400
    (ev,) = recorder.events
    assert ev.status == "rejected" and ev.source == "url" and ev.schema_name == "http://127.0.0.1/x.xsd"


def test_health_emits_nothing(client: TestClient, recorder: ListRecorder) -> None:
    assert client.get("/api/health").status_code == 200
    assert recorder.events == [] and recorder.drains == 0


def test_no_tracker_installed_is_fine(simple_xsd_bytes: bytes) -> None:
    assert not hasattr(app.state, "usage")
    r = TestClient(app).post("/api/schema/text", json={"content": simple_xsd_bytes.decode()})
    assert r.status_code == 200


def test_lifespan_with_disabled_settings() -> None:
    with TestClient(app) as c:
        assert c.app.state.usage.enabled is False
        assert c.get("/api/health").status_code == 200
