"""Security-critical parser and network helpers.

Every ``lxml`` call goes through :func:`parse_bytes` so that external
entities, DTD loading and network access at parse-time are globally off.
The only DTD markup accepted is a bounded internal subset of literal-value
entities (see :func:`inspect_dtd`), which some W3C schemas rely on.
URL fetching for ``schemaLocation`` references goes through
:func:`fetch_schema_url`, which restricts schemes to http(s), blocks
private IP ranges, caps response size and limits redirects. Hosts are
allowed by default; setting ``ALLOWED_SCHEMA_HOSTS`` switches to a strict
whitelist (lockdown mode) for hardened deployments.
"""

from __future__ import annotations

import ipaddress
import logging
import re
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


def make_parser(*, internal_entities: bool = False) -> etree.XMLParser:
    """Return a parser configured to block XXE and external network access.

    - ``resolve_entities`` is off by default (no entity substitution ⇒ no XXE).
      It is switched on only for documents whose DOCTYPE passed
      :func:`inspect_dtd` — a bounded internal subset of literal-value
      entities, which is what the W3C xmldsig/xenc schemas ship with.
    - ``no_network=True`` forbids the parser from fetching DTDs/entities.
    - ``load_dtd=False`` never loads an external DTD subset, even when the
      DOCTYPE names one via SYSTEM/PUBLIC.
    - ``huge_tree=False`` leaves lxml's internal XML-bomb mitigations active.
    - ``remove_comments=False`` so comments are preserved in the tree; we
      want to show them in the viewer.
    """
    return etree.XMLParser(
        resolve_entities=internal_entities,
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
    has_safe_subset = inspect_dtd(data)
    parser = make_parser(internal_entities=has_safe_subset)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        if "Detected an entity reference loop" in str(exc) or "Entities" in str(exc):
            raise SecurityError(f"rejected dangerous XML construct: {exc}") from exc
        raise
    return etree.ElementTree(root)


# ---------------------------------------------------------------------------
# DOCTYPE inspection
# ---------------------------------------------------------------------------

DTD_HEAD_BYTES = 16 * 1024
MAX_DTD_DECLARATIONS = 32
MAX_ENTITY_VALUE_CHARS = 512

_DTD_TOKENS = (b"<!DOCTYPE", b"<!ENTITY", b"<!ATTLIST", b"<!NOTATION", b"<!ELEMENT")
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE\b(?P<header>[^\[>]*)(?:\[(?P<subset>.*?)\]\s*)?>", re.S)
_COMMENT_RE = re.compile(rb"<!--.*?-->", re.S)
_DECL_RE = re.compile(rb"<!(?P<kind>ENTITY|ATTLIST)\b(?P<body>[^>]*)>", re.S)
_ENTITY_BODY_RE = re.compile(
    rb"^\s*(?:%\s+)?[A-Za-z_:][\w.:-]*\s+(?P<q>[\"'])(?P<value>[^\"']*)(?P=q)\s*$", re.S
)
_UNSAFE_IN_VALUE = re.compile(rb"[&%<]")

DTD_REJECTED_MESSAGE = (
    "DTD constructs are not allowed in uploads (only a DOCTYPE with simple, literal-value "
    "<!ENTITY> declarations is accepted); remove the DOCTYPE and inline the entity values"
)


def inspect_dtd(data: bytes) -> bool:
    """Return True when ``data`` carries a DOCTYPE that is safe to expand.

    Accepted: at most one DOCTYPE (with or without a PUBLIC/SYSTEM external
    id — the parser never loads it) whose internal subset contains only
    comments plus ≤ ``MAX_DTD_DECLARATIONS`` ``<!ENTITY>`` / ``<!ATTLIST>``
    declarations with literal values that reference nothing (no ``&``, ``%``
    or ``<``). That rules out XXE, billion-laughs nesting and injected
    markup while letting the W3C xmldsig/xenc schemas through.

    Raises :class:`SecurityError` for everything else that looks like DTD
    markup; returns False when there is no DTD at all.
    """
    head = data[:DTD_HEAD_BYTES]
    upper = head.upper()
    if not any(token in upper for token in _DTD_TOKENS):
        return False
    match = _DOCTYPE_RE.search(head)
    if match is None:
        raise SecurityError(DTD_REJECTED_MESSAGE)
    remainder = head[: match.start()] + head[match.end() :]
    if any(token in remainder.upper() for token in _DTD_TOKENS):
        raise SecurityError(DTD_REJECTED_MESSAGE)
    subset = _COMMENT_RE.sub(b"", match.group("subset") or b"")
    declarations = 0
    pos = 0
    for decl in _DECL_RE.finditer(subset):
        if subset[pos : decl.start()].strip():
            raise SecurityError(DTD_REJECTED_MESSAGE)
        pos = decl.end()
        declarations += 1
        body = decl.group("body")
        if decl.group("kind") == b"ENTITY":
            entity = _ENTITY_BODY_RE.match(body)
            if entity is None or len(entity.group("value")) > MAX_ENTITY_VALUE_CHARS:
                raise SecurityError(DTD_REJECTED_MESSAGE)
            body = entity.group("value")
        if _UNSAFE_IN_VALUE.search(body):
            raise SecurityError(DTD_REJECTED_MESSAGE)
    if subset[pos:].strip() or declarations > MAX_DTD_DECLARATIONS:
        raise SecurityError(DTD_REJECTED_MESSAGE)
    return True


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
