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
    def test_url_without_allowlist_rejected(self) -> None:
        with patch.object(config_module.settings, "allowed_schema_hosts", ()):
            from app.parser import security as sec_module

            sec_module.settings = config_module.settings  # propagate
            with pytest.raises(SecurityError, match="not on ALLOWED_SCHEMA_HOSTS"):
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
        import re as re_module

        with patch.object(
            config_module.settings,
            "allowed_schema_hosts",
            (re_module.compile(r".*"),),
        ):
            from app.parser import security as sec_module

            sec_module.settings = config_module.settings
            with pytest.raises(SecurityError, match="only http"):
                fetch_schema_url("file:///etc/passwd")
