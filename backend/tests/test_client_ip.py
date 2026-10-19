from __future__ import annotations

import pytest
from starlette.requests import Request

from app.config import settings
from app.rate_limit import client_ip


def _request(forwarded: str | None, peer: str = "10.0.0.9") -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [
        ("198.51.100.7", "198.51.100.7"),
        # The client made up the left part; the proxy appended the real address.
        ("8.8.8.8, 198.51.100.7", "198.51.100.7"),
        ("1.1.1.1,2.2.2.2 , 198.51.100.7", "198.51.100.7"),
        (None, "10.0.0.9"),
        ("", "10.0.0.9"),
    ],
)
def test_client_ip_trusts_only_the_proxy_entry(forwarded: str | None, expected: str) -> None:
    assert client_ip(_request(forwarded)) == expected


def test_client_ip_without_proxy_uses_the_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert client_ip(_request("8.8.8.8")) == "10.0.0.9"


def test_client_ip_counts_several_proxies_from_the_right(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    assert client_ip(_request("8.8.8.8, 198.51.100.7, 35.191.0.1")) == "198.51.100.7"
