from __future__ import annotations

from app.usage.context import RequestUsage, UsageTracker, bind, emit, unbind
from app.usage.events import UsageEvent
from app.usage.recorder import UsageRecorder


class ListRecorder(UsageRecorder):
    def __init__(self) -> None:
        super().__init__("postgresql://fake")
        self.events: list[UsageEvent] = []

    def record(self, event: UsageEvent) -> bool:
        self.events.append(event)
        return True


def test_emit_without_context_is_noop() -> None:
    assert emit("page_view", path="/") is False


def test_emit_builds_event() -> None:
    rec = ListRecorder()
    tracker = UsageTracker(rec, geoip=None, hash_secret="s")
    token = bind(
        RequestUsage(tracker, ip="1.2.3.4", user_agent="curl/8.0", referrer="https://a.example/x?q=1")
    )
    try:
        assert emit("schema_load", source="upload", schema_name="a.xsd", status="ok", error_detail="x" * 999)
    finally:
        unbind(token)
    (ev,) = rec.events
    assert ev.event_type == "schema_load" and ev.source == "upload"
    assert ev.visitor_hash and "1.2.3.4" not in ev.visitor_hash
    assert ev.device == "bot" and ev.referrer == "https://a.example/x"
    assert ev.country_code is None and ev.app_version
    assert len(ev.error_detail) == 255


def test_emit_disabled_tracker() -> None:
    tracker = UsageTracker(UsageRecorder(""), geoip=None, hash_secret="")
    token = bind(RequestUsage(tracker, "1.1.1.1", None, None))
    try:
        assert emit("page_view", path="/") is False
    finally:
        unbind(token)
