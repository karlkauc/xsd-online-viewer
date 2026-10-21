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
        assert classify_device("Mozilla/5.0 (Windows NT 10.0) Chrome/138.0.0.0 Safari/537.36") == "desktop"
        assert classify_device("Mozilla/5.0 (Windows NT 6.1) Chrome/109.0.0.0 Safari/537.36") == "desktop"

    def test_scanners_posing_as_browsers(self) -> None:
        for ua in (
            "Mozilla/5.0 (compatible; intex-v2-check/0.1)",
            "CoinCreatorScanner/1.0 (new-zones node; +https://tx.coincreator.io)",
            "nameserver-checker-http-validator/1.0",
            "siteradar/0.1-contact:ops@example.org",
            "GoogleOther",
            "Mozilla/5.0 (compatible; ShinkiHPBot/1.0; +lead-research)",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) Chrome/33.0.1750.152 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:21.0) Gecko/20130331 Firefox/21.0",
            "Mozilla/5.0 (compatible; CensysInspect/1.1; +https://about.censys.io/)",
            "Hello from Palo Alto Networks, find out more about our scans in https://docs-cortex.paloaltonetworks.com",
            "Mozilla/5.0 (compatible; Palo Alto Networks)",
            "Mozilla/5.0 zgrab/0.x",
            "Mozilla/5.0 (compatible; Nuclei - Open-source project (github.com/projectdiscovery/nuclei))",
            "Mozilla/5.0 (compatible) python-urllib3/2.2",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/12.1.2 Safari/605.1.15",
        ):
            assert classify_device(ua) == "bot", ua
        assert classify_device("") == "unknown"
        assert classify_device(None) == "unknown"

    def test_current_safari_stays_human(self) -> None:
        iphone = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS {} like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        )
        ios17 = iphone.format("17_5") + "Version/17.5 Mobile/15E148 Safari/604.1"
        ios18 = iphone.format("18_1") + "Version/18.1 Mobile/15E148 Safari/604.1"
        crios = iphone.format("17_5") + "CriOS/126.0.6478.54 Mobile/15E148 Safari/604.1"
        mac17 = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.4.1 Safari/605.1.15"
        )
        webview = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Version/4.0 Chrome/126.0.6478.71 Mobile Safari/537.36"
        )
        assert classify_device(ios17) == "mobile"
        assert classify_device(ios18) == "mobile"
        assert classify_device(mac17) == "desktop"
        assert classify_device(crios) == "mobile"
        assert classify_device(webview) == "mobile"


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

    def test_url_drops_credentials(self) -> None:
        name = schema_display_name("url", "https://bob:s3cret@h.example:8443/x.xsd")
        assert name == "https://h.example:8443/x.xsd"

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


def test_utm_fields_keep_only_short_slugs() -> None:
    from app.usage.events import utm_fields

    assert utm_fields({"utm_source": "OData-Viewer", "utm_medium": "sister", "other": "x"}) == {
        "utm_source": "odata-viewer",
        "utm_medium": "sister",
    }
    assert utm_fields({"utm_source": "a b", "utm_campaign": "x" * 65}) == {}
