"""ISO 20022 tab: catalogue, loading by message id from the pinned mirror."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import app.api.iso20022 as iso_module
from app.api.iso20022 import catalog, message_url
from app.content.pages import all_pages
from app.main import app
from app.parser.security import FetchedResource

XSD = b"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.12"
  targetNamespace="urn:iso:std:iso:20022:tech:xsd:pain.001.001.12" elementFormDefault="qualified">
  <xs:element name="Document" type="Document"/>
  <xs:complexType name="Document"><xs:sequence>
    <xs:element name="CstmrCdtTrfInitn" type="xs:string"/>
  </xs:sequence></xs:complexType>
</xs:schema>"""


def test_catalog_is_complete_and_pinned() -> None:
    c = catalog()
    ids = [m.id for m in c.messages]
    assert len(ids) > 300 and len(ids) == len(set(ids))
    assert re.fullmatch(r"https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/", c.source.base_url)
    assert all(m.name and m.root for m in c.messages)
    assert {"pain.001.001.12", "camt.053.001.12", "pacs.008.001.13"} <= set(ids)


def test_messages_endpoint() -> None:
    body = TestClient(app).get("/api/iso20022/messages").json()
    assert body["source"]["commit"] and len(body["messages"]) == len(catalog().messages)


def test_load_fetches_the_pinned_url_only(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[str] = []

    def fake_fetch(url: str) -> FetchedResource:
        fetched.append(url)
        return FetchedResource(url=url, content=XSD, content_type="application/xml")

    monkeypatch.setattr(iso_module, "fetch_schema_url", fake_fetch)
    r = TestClient(app).post("/api/iso20022/pain.001.001.12/load")
    assert r.status_code == 200, r.text
    message = next(m for m in catalog().messages if m.id == "pain.001.001.12")
    assert fetched == [message_url(message)]
    assert any(e["name"] == "Document" for e in r.json()["model"]["elements"])


def test_unknown_message_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso_module, "fetch_schema_url", lambda url: pytest.fail("must not fetch"))
    client = TestClient(app)
    assert client.post("/api/iso20022/pain.999.001.01/load").status_code == 404
    assert client.post("/api/iso20022/..%2F..%2Fetc/load").status_code == 404


def test_content_pages_link_existing_messages() -> None:
    ids = {m.id for m in catalog().messages}
    linked = set()
    for slug, page in all_pages().items():
        if slug.startswith("standards/"):
            linked |= set(re.findall(r"/iso20022\?message=([a-z0-9.]+)", page.body + (page.cta_href or "")))
    assert linked and linked <= ids
