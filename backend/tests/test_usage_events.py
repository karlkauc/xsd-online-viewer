from __future__ import annotations

from datetime import date

from app.usage.events import (
    COLUMNS,
    INSERT_SQL,
    UsageEvent,
    classify_device,
    clean_referrer,
    schema_display_name,
    visitor_hash,
)

DAY = date(2026, 8, 25)
UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0"


class TestVisitorHash:
    def test_stable_within_day(self) -> None:
        assert visitor_hash("1.2.3.4", UA, DAY, "s") == visitor_hash("1.2.3.4", UA, DAY, "s")

    def test_changes_with_day_secret_ip_ua(self) -> None:
        base = visitor_hash("1.2.3.4", UA, DAY, "s")
        assert base != visitor_hash("1.2.3.4", UA, date(2026, 8, 26), "s")
        assert base != visitor_hash("1.2.3.4", UA, DAY, "other")
        assert base != visitor_hash("1.2.3.5", UA, DAY, "s")
        assert base != visitor_hash("1.2.3.4", "curl/8", DAY, "s")

    def test_never_contains_ip(self) -> None:
        h = visitor_hash("1.2.3.4", UA, DAY, "")
        assert h is not None and "1.2.3.4" not in h and len(h) == 32

    def test_no_ip_gives_none(self) -> None:
        assert visitor_hash(None, UA, DAY, "s") is None


class TestDevice:
    def test_classification(self) -> None:
        assert classify_device(UA) == "desktop"
        assert classify_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148") == "mobile"
        assert classify_device("Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile") == "mobile"
        assert classify_device("Mozilla/5.0 (compatible; Googlebot/2.1)") == "bot"
        assert classify_device("curl/8.4.0") == "bot"
        assert classify_device("python-requests/2.32") == "bot"
        assert classify_device("") == "unknown"
        assert classify_device(None) == "unknown"


class TestReferrer:
    def test_strips_query_and_fragment(self) -> None:
        assert clean_referrer("https://www.google.com/search?q=xsd#x") == "https://www.google.com/search"

    def test_root_path(self) -> None:
        assert clean_referrer("https://example.org") == "https://example.org/"

    def test_keeps_port_drops_credentials(self) -> None:
        assert clean_referrer("http://user:pw@host:8080/p?x=1") == "http://host:8080/p"

    def test_invalid(self) -> None:
        assert clean_referrer(None) is None
        assert clean_referrer("") is None
        assert clean_referrer("not a url") is None
        assert clean_referrer("ftp://host/x") is None


class TestSchemaName:
    def test_upload_basename(self) -> None:
        assert schema_display_name("upload", "C:\\Users\\k\\schema.xsd") == "schema.xsd"
        assert schema_display_name("text", "/tmp/a/b.xsd") == "b.xsd"

    def test_url_without_query(self) -> None:
        assert (
            schema_display_name("url", "https://h.example/x/y.xsd?token=1#f")
            == "https://h.example/x/y.xsd"
        )

    def test_release_and_empty(self) -> None:
        assert schema_display_name("release", "v4.2.2/FundsXML4.xsd") == "v4.2.2/FundsXML4.xsd"
        assert schema_display_name("upload", "") is None

    def test_truncated(self) -> None:
        assert len(schema_display_name("upload", "a" * 1000) or "") == 255


class TestRow:
    def test_row_matches_columns(self) -> None:
        ev = UsageEvent(event_type="page_view", path="/")
        row = ev.as_row()
        assert len(row) == len(COLUMNS)
        assert row[COLUMNS.index("event_type")] == "page_view"
        assert row[COLUMNS.index("path")] == "/"
        assert INSERT_SQL.count("%s") == len(COLUMNS)
