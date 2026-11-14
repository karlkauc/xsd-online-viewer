"""Large schema loads: fetch once per URL, import budget, gzip, one parse at a time.

The out-of-memory kills of 10–11/2026 came from schema sets whose loads ran
long or produced huge responses, and from the visitor's retry running a second
parse alongside the first (see ``UrlResolver``, ``ingest_schema``).
"""

from __future__ import annotations

from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import schema as schema_api
from app.config import settings
from app.main import app
from app.parser import xsd_parser
from app.parser.security import FetchedResource, FetchSession, SecurityError, fetch_schema_url
from app.parser.xsd_parser import ImportBudgetError, parse_with_url_fallback

BASE = "https://example.org/xsd/"


def _xsd(name: str, *includes: str) -> bytes:
    refs = "".join(f'<xs:include schemaLocation="{inc}"/>' for inc in includes)
    return (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'targetNamespace="urn:t" xmlns="urn:t" elementFormDefault="qualified">'
        f'{refs}<xs:element name="{name}" type="xs:string"/></xs:schema>'
    ).encode()


# main includes a and b; both include common, which a third of the set does in NeTEx.
SERVED = {
    "main.xsd": _xsd("Main", "a.xsd", "b.xsd", "missing.xsd"),
    "a.xsd": _xsd("A", "common.xsd", "missing.xsd"),
    "b.xsd": _xsd("B", "common.xsd", "missing.xsd"),
    "common.xsd": _xsd("Common"),
}


@pytest.fixture
def fetches(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    seen: Counter[str] = Counter()

    def fake_fetch(url: str, session: FetchSession | None = None) -> FetchedResource:
        seen[url] += 1
        name = url.removeprefix(BASE)
        if name not in SERVED:
            raise SecurityError(f"fetching {url!r} failed with HTTP 404 Not Found")
        return FetchedResource(url=url, content=SERVED[name], content_type="text/xml")

    monkeypatch.setattr(xsd_parser, "fetch_schema_url", fake_fetch)
    return seen


def _load_main():
    return parse_with_url_fallback(
        zip_bytes=None,
        main_filename=BASE + "main.xsd",
        main_bytes=SERVED["main.xsd"],
        base_url=BASE + "main.xsd",
    )


def test_each_url_is_fetched_once_per_parse(fetches: Counter[str]) -> None:
    model = _load_main()
    assert {e.name for e in model.elements} == {"Main", "A", "B", "Common"}
    assert fetches == Counter({BASE + n: 1 for n in ("a.xsd", "b.xsd", "common.xsd", "missing.xsd")})
    # A failed fetch is not retried, yet every reference to it is still reported.
    warnings = [d.message for d in model.diagnostics if "missing.xsd" in d.message]
    assert len(warnings) == 3


def test_import_budget_stops_a_load_that_cannot_finish(
    fetches: Counter[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "import_fetch_budget_seconds", -1.0)
    with pytest.raises(ImportBudgetError, match=r"longer than -1 s \(1 fetched so far\).*ZIP"):
        _load_main()
    assert sum(fetches.values()) == 1


def test_import_budget_is_a_400_for_the_visitor(
    fetches: Counter[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "import_fetch_budget_seconds", -1.0)
    monkeypatch.setattr(
        schema_api,
        "fetch_schema_url",
        lambda url: FetchedResource(url=url, content=SERVED["main.xsd"], content_type="text/xml"),
    )
    response = TestClient(app).post("/api/schema/url", json={"url": BASE + "main.xsd"})
    assert response.status_code == 400
    assert "upload it instead" in response.json()["detail"]


class TestFetchSession:
    XSD = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'

    @pytest.fixture
    def clients(self, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Client]:
        from app.parser import security as sec_module

        monkeypatch.setattr(sec_module, "_verify_url", lambda url: (httpx.URL(url).host, ["203.0.113.10"]))
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=self.XSD))
        real_client = httpx.Client
        made: list[httpx.Client] = []

        def client_factory(**kwargs):
            client = real_client(transport=transport, **kwargs)
            made.append(client)
            return client

        monkeypatch.setattr(sec_module.httpx, "Client", client_factory)
        return made

    def test_one_client_per_host_and_closed_at_the_end(self, clients: list[httpx.Client]) -> None:
        with FetchSession() as session:
            fetch_schema_url("https://example.org/a.xsd", session=session)
            fetch_schema_url("https://example.org/b.xsd", session=session)
            # Same IP, other host: never the first host's connection (SNI/certificate).
            fetch_schema_url("https://example.net/c.xsd", session=session)
            assert len(clients) == 2
        assert all(client.is_closed for client in clients)

    def test_without_a_session_nothing_stays_open(self, clients: list[httpx.Client]) -> None:
        fetch_schema_url("https://example.org/a.xsd")
        assert len(clients) == 1 and clients[0].is_closed


def test_large_json_responses_are_gzipped(simple_xsd_bytes: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/schema/upload", files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")}
    )
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["schema_id"]


def test_parses_queue_and_give_up_after_the_wait(
    simple_xsd_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(schema_api, "PARSE_WAIT_SECONDS", 0.05)
    client = TestClient(app)
    with schema_api._PARSE_SLOT:
        response = client.post(
            "/api/schema/upload", files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")}
        )
    assert response.status_code == 503
    assert "busy" in response.json()["detail"]
    retry = client.post(
        "/api/schema/upload", files={"file": ("simple.xsd", simple_xsd_bytes, "application/xml")}
    )
    assert retry.status_code == 200


def test_cache_counts_the_models_real_footprint(
    simple_xsd_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    sizes: list[int] = []
    real_put = schema_api.schema_cache.put
    monkeypatch.setattr(
        schema_api.schema_cache,
        "put",
        lambda key, value, size=0: (sizes.append(size), real_put(key, value, size)),
    )
    response = schema_api.finalize_schema_response(xsd_parser.parse_single(simple_xsd_bytes, "simple.xsd"))
    # Measured before the schema id is filled in, hence approx.
    json_bytes = len(response.model.model_dump_json().encode())
    assert sizes == [pytest.approx(json_bytes * schema_api.MODEL_BYTES_PER_JSON_BYTE, rel=0.01)]
