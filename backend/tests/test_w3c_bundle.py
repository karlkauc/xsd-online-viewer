"""Bundled W3C schemas (app/parser/w3c): imports of xml.xsd, xmldsig, xenc and
xlink resolve offline, for parsing and for validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser import w3c
from app.parser.xsd_parser import parse_files_map, parse_single, parse_with_url_fallback

FIXTURES = Path(__file__).parent / "fixtures"
XS = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'

XML_NS_IMPORT_BY_NAMESPACE = f"""<?xml version="1.0"?>
<xs:schema {XS} xmlns:xml="http://www.w3.org/XML/1998/namespace" targetNamespace="urn:t" xmlns:t="urn:t">
  <xs:import namespace="http://www.w3.org/XML/1998/namespace"/>
  <xs:element name="Text"><xs:complexType><xs:attribute ref="xml:lang"/></xs:complexType></xs:element>
</xs:schema>""".encode()

DSIG_IMPORT_BY_ABSOLUTE_URL = f"""<?xml version="1.0"?>
<xs:schema {XS} xmlns:ds="http://www.w3.org/2000/09/xmldsig#" targetNamespace="urn:h" xmlns:h="urn:h"
    elementFormDefault="qualified">
  <xs:import namespace="http://www.w3.org/2000/09/xmldsig#"
      schemaLocation="http://www.w3.org/TR/2002/REC-xmldsig-core-20020212/xmldsig-core-schema.xsd"/>
  <xs:element name="Doc"><xs:complexType><xs:sequence>
    <xs:element name="Body" type="xs:string"/>
    <xs:element ref="ds:Signature" minOccurs="0"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>""".encode()


def _unresolved(model) -> list[str]:
    return [
        d.message for d in model.diagnostics if "unresolved" in d.message or "could not load" in d.message
    ]


class TestLookup:
    def test_namespaces_and_locations(self) -> None:
        assert w3c.bytes_for_namespace("http://www.w3.org/2000/09/xmldsig#") is not None
        assert w3c.bytes_for_namespace("http://www.w3.org/2001/04/xmlenc#") is not None
        assert w3c.bytes_for_namespace("http://www.w3.org/1999/xlink") is not None
        assert w3c.bytes_for_namespace("http://www.w3.org/XML/1998/namespace") is not None
        assert w3c.bytes_for_namespace("urn:not-bundled") is None
        located = w3c.bytes_for_location("http://www.w3.org/2001/xml.xsd")
        assert located is not None and located[0] == "xml.xsd"
        assert w3c.bytes_for_location("../common/xmldsig-core-schema.xsd") is not None
        assert w3c.bytes_for_location("xmldsig-core-schema.xsd?raw=1") is not None
        assert w3c.bytes_for_location("mine.xsd") is None

    def test_bundled_files_are_the_w3c_originals(self) -> None:
        _, content = w3c.bytes_for_namespace("http://www.w3.org/2000/09/xmldsig#")
        assert content == (FIXTURES / "xmldsig-core-schema.xsd").read_bytes()


class TestParserResolution:
    def test_single_upload_importing_xmldsig_by_filename(self) -> None:
        model = parse_single((FIXTURES / "imports-dsig.xsd").read_bytes(), "imports-dsig.xsd")
        assert _unresolved(model) == []
        imported = [f for f in model.files if f.relationship == "import"]
        assert [f.filename for f in imported] == ["xmldsig-core-schema.xsd"]
        assert "element:{http://www.w3.org/2000/09/xmldsig#}Signature" in {e.id for e in model.elements}

    def test_import_by_namespace_without_location(self) -> None:
        model = parse_single(XML_NS_IMPORT_BY_NAMESPACE, "t.xsd")
        assert _unresolved(model) == []
        assert [f.filename for f in model.files if f.relationship == "import"] == ["xml.xsd"]

    def test_absolute_w3c_url_is_served_offline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.parser import xsd_parser

        def no_network(url: str):
            raise AssertionError(f"network fetch attempted: {url}")

        monkeypatch.setattr(xsd_parser, "fetch_schema_url", no_network)
        model = parse_with_url_fallback(
            zip_bytes=None,
            main_filename="https://example.org/h.xsd",
            main_bytes=DSIG_IMPORT_BY_ABSOLUTE_URL,
            base_url="https://example.org/h.xsd",
        )
        assert _unresolved(model) == []
        assert "element:{http://www.w3.org/2000/09/xmldsig#}Signature" in {e.id for e in model.elements}

    def test_a_shipped_copy_wins_over_the_bundle(self) -> None:
        own_xml_xsd = (
            f'<xs:schema {XS} targetNamespace="http://www.w3.org/XML/1998/namespace" '
            'xmlns:xml="http://www.w3.org/XML/1998/namespace">'
            '<xs:attribute name="lang" type="xs:string"/><xs:attribute name="mine" type="xs:string"/>'
            "</xs:schema>"
        ).encode()
        main = XML_NS_IMPORT_BY_NAMESPACE.replace(
            b'<xs:import namespace="http://www.w3.org/XML/1998/namespace"/>',
            b'<xs:import namespace="http://www.w3.org/XML/1998/namespace" schemaLocation="xml.xsd"/>',
        )
        model = parse_files_map({"t.xsd": main, "xml.xsd": own_xml_xsd}, "t.xsd")
        (xml_file,) = [f for f in model.files if f.filename == "xml.xsd"]
        assert xml_file.content is not None and 'name="mine"' in xml_file.content


class TestValidationUsesBundle:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_validate_against_lone_upload_importing_xmldsig(self, client: TestClient) -> None:
        upload = client.post(
            "/api/schema/upload",
            files={"file": ("imports-dsig.xsd", (FIXTURES / "imports-dsig.xsd").read_bytes(), "text/xml")},
        )
        assert upload.status_code == 200, upload.text
        schema_id = upload.json()["schema_id"]
        response = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": '<Document xmlns="http://example.com/host"><Body>x</Body><Footer>f</Footer></Document>'},
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True

    def test_validate_against_import_by_absolute_w3c_url(self, client: TestClient) -> None:
        payload = {"filename": "h.xsd", "content": DSIG_IMPORT_BY_ABSOLUTE_URL.decode()}
        upload = client.post("/api/schema/text", json=payload)
        assert upload.status_code == 200, upload.text
        schema_id = upload.json()["schema_id"]
        response = client.post(
            f"/api/schema/{schema_id}/validate/text",
            json={"content": '<Doc xmlns="urn:h"><Body>x</Body></Doc>'},
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True
