"""Security-critical parser and network helpers.

Every ``lxml`` call goes through :func:`make_parser` so that external
entities, DTD loading and network access at parse-time are globally off.
URL fetching for ``schemaLocation`` references goes through
:func:`fetch_schema_url`, which restricts schemes to http(s), blocks
private IP ranges, caps response size and limits redirects. Hosts are
allowed by default; setting ``ALLOWED_SCHEMA_HOSTS`` switches to a strict
whitelist (lockdown mode) for hardened deployments.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass

import httpx
from lxml import etree

from app.config import settings

logger = logging.getLogger(__name__)


class SecurityError(ValueError):
    """Raised when an upload or URL violates security policy."""


# ---------------------------------------------------------------------------
# Hardened lxml parser
# ---------------------------------------------------------------------------


def make_parser() -> etree.XMLParser:
    """Return a parser configured to block XXE and external network access.

    - ``resolve_entities=False`` disables entity substitution (XXE).
    - ``no_network=True`` forbids the parser from fetching DTDs/entities.
    - ``load_dtd=False`` skips DTD processing entirely.
    - ``huge_tree=False`` leaves lxml's internal XML-bomb mitigations active.
    - ``remove_comments=False`` so comments are preserved in the tree; we
      want to show them in the viewer.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        huge_tree=False,
        remove_blank_text=False,
        remove_comments=False,
        recover=False,
    )


def parse_bytes(data: bytes, filename: str | None = None) -> etree._ElementTree:
    """Parse XML bytes with the hardened parser, raising ``SecurityError``
    on DTD / external entity constructs.
    """
    _reject_known_bombs(data)
    parser = make_parser()
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        if "Detected an entity reference loop" in str(exc) or "Entities" in str(exc):
            raise SecurityError(f"rejected dangerous XML construct: {exc}") from exc
        raise
    return etree.ElementTree(root)


_BANNED_TOKENS = (b"<!DOCTYPE", b"<!ENTITY", b"<!ATTLIST", b"<!NOTATION")


def _reject_known_bombs(data: bytes) -> None:
    # Cheap pre-filter: any DTD markup inside an XSD is either unnecessary
    # (XSDs should not carry DTDs) or a vector for a billion-laughs attack.
    head = data[:4096].upper()
    for token in _BANNED_TOKENS:
        if token in head:
            raise SecurityError(f"DTD construct {token.decode()!r} is not permitted in uploads")


# ---------------------------------------------------------------------------
# SSRF-protected URL fetcher
# ---------------------------------------------------------------------------


@dataclass
class FetchedResource:
    url: str
    content: bytes
    content_type: str | None


def _host_is_allowed(host: str) -> bool:
    # Empty allowlist means "any host permitted" (default-open). Setting
    # ALLOWED_SCHEMA_HOSTS turns this into a strict lockdown whitelist.
    if not settings.allowed_schema_hosts:
        return True
    return any(pattern.search(host) for pattern in settings.allowed_schema_hosts)


def _ip_is_private(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True  # treat unparseable as unsafe
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_all_addrs(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise SecurityError(f"DNS resolution failed for {host!r}: {exc}") from exc
    return list({info[4][0] for info in infos})


def _verify_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityError(f"only http(s) schemes are permitted; got {parsed.scheme!r}")
    host = parsed.host
    if not host:
        raise SecurityError(f"URL has no host: {url!r}")
    if not _host_is_allowed(host):
        raise SecurityError(
            f"host {host!r} is not on ALLOWED_SCHEMA_HOSTS lockdown whitelist"
        )
    for addr in _resolve_all_addrs(host):
        if _ip_is_private(addr):
            raise SecurityError(
                f"host {host!r} resolves to a private/loopback address ({addr}); refusing to fetch"
            )


def fetch_schema_url(url: str) -> FetchedResource:
    """Fetch a schema document by URL, enforcing all SSRF mitigations."""
    _verify_url(url)
    remaining_redirects = settings.fetch_max_redirects
    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=settings.fetch_timeout_seconds,
        limits=httpx.Limits(max_connections=4),
    ) as client:
        while True:
            response = client.get(current)
            if response.is_redirect:
                if remaining_redirects <= 0:
                    raise SecurityError("too many HTTP redirects")
                remaining_redirects -= 1
                target = response.headers.get("location")
                if not target:
                    raise SecurityError("redirect without Location header")
                current = str(httpx.URL(current).join(target))
                _verify_url(current)
                continue
            if response.status_code >= 400:
                raise SecurityError(
                    f"fetching {current!r} failed with HTTP {response.status_code}"
                )
            content = response.content
            if len(content) > settings.fetch_max_response_bytes:
                raise SecurityError(
                    f"response from {current!r} exceeds "
                    f"{settings.fetch_max_response_mb} MB cap"
                )
            logger.info(
                "fetched remote schema",
                extra={
                    "ctx_url": current,
                    "ctx_size_bytes": len(content),
                    "ctx_content_type": response.headers.get("content-type"),
                },
            )
            return FetchedResource(
                url=current,
                content=content,
                content_type=response.headers.get("content-type"),
            )
