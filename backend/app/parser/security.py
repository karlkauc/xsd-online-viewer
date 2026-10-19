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
import time
from dataclasses import dataclass

import httpx
from lxml import etree

from app import __version__
from app.config import settings
from app.parser.urls import normalize_schema_url

logger = logging.getLogger(__name__)


class SecurityError(ValueError):
    """Raised when an upload or URL violates security policy."""


class FetchError(SecurityError):
    """A remote fetch failed at the transport level (DNS, TLS, timeout, refused).

    Not a policy violation, but raised as a ``SecurityError`` subclass so every
    caller that already turns policy rejections into a 400 / import warning
    handles network failures the same way instead of surfacing a 500.
    """


# Some hosts (w3schools, for one) answer 403 to httpx's default User-Agent.
USER_AGENT = f"xsd-viewer.online/{__version__} (+https://www.xsd-viewer.online)"
FETCH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/xml, text/xml;q=0.9, */*;q=0.5",
}


# ---------------------------------------------------------------------------
# Hardened lxml parser
# ---------------------------------------------------------------------------


def make_parser(*, internal_entities: bool = False, recover: bool = False) -> etree.XMLParser:
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
    - ``collect_ids`` stays at its default: switching it off sets libxml2's
      ``XML_SKIP_IDS`` bit in ``loadsubset``, which libxml2 2.14 reads as "load
      the external DTD subset" — exactly what ``load_dtd=False`` forbids.
    - ``recover`` is only ever set by :func:`parse_bytes`, for a document
      whose sole fault is a repeated ID.
    """
    return etree.XMLParser(
        # "internal" never substitutes an external entity, even if inspect_dtd were fooled.
        resolve_entities="internal" if internal_entities else False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        huge_tree=False,
        remove_blank_text=False,
        remove_comments=False,
        recover=recover,
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
        if not only_duplicate_ids(parser):
            raise
        # The strict pass logged nothing else, so recovery has nothing to
        # paper over: it only keeps lxml from raising on the validity error.
        root = etree.fromstring(data, make_parser(internal_entities=has_safe_subset, recover=True))
    return etree.ElementTree(root)


def only_duplicate_ids(parser: etree.XMLParser) -> bool:
    """True when ``parser``'s last parse failed on nothing but "ID … already defined".

    libxml2 registers every ``xml:id`` and DTD-typed ID attribute while
    parsing and reports a repeat as a validity error; the document is still
    well-formed and fully parsed, but lxml raises on any logged error. Schemas
    with such repeats are in circulation, and a viewer should show them.

    Reads the parser's own log: the one on the exception also carries entries
    of earlier operations on the same thread (a schema compile, for one).
    """
    errors = [entry for entry in parser.error_log if entry.level >= etree.ErrorLevels.ERROR]
    return bool(errors) and all(entry.type == etree.ErrorTypes.DTD_ID_REDEFINED for entry in errors)


# ---------------------------------------------------------------------------
# DOCTYPE inspection
# ---------------------------------------------------------------------------

DTD_HEAD_BYTES = 16 * 1024
MAX_DTD_DECLARATIONS = 32
MAX_ENTITY_VALUE_CHARS = 512

_DTD_TOKENS = (b"<!DOCTYPE", b"<!ENTITY", b"<!ATTLIST", b"<!NOTATION", b"<!ELEMENT")
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE\b(?P<header>[^\[>]*)(?:\[(?P<subset>.*?)\]\s*)?>", re.S)
_DECL_RE = re.compile(rb"<!(?P<kind>ENTITY|ATTLIST)\b(?P<body>[^>]*)>", re.S)
_ENTITY_BODY_RE = re.compile(
    rb"^\s*(?:%\s+)?[A-Za-z_:][\w.:-]*\s+(?P<q>[\"'])(?P<value>[^\"']*)(?P=q)\s*$", re.S
)
_UNSAFE_IN_VALUE = re.compile(rb"[&%<]")

DTD_REJECTED_MESSAGE = (
    "DTD constructs are not allowed in uploads (only a DOCTYPE with simple, literal-value "
    "<!ENTITY> declarations is accepted); remove the DOCTYPE and inline the entity values"
)


def _strip_comments(subset: bytes) -> bytes:
    """Drop ``<!--…-->`` from a DTD subset, but never inside a quoted literal.

    A quote-blind regex let ``<!ENTITY a "<!--"> <!ENTITY x SYSTEM …> <!ENTITY b "-->">``
    pass as one harmless entity while libxml2 saw the external one.
    """
    out = bytearray()
    quote: int | None = None
    i = 0
    while i < len(subset):
        ch = subset[i]
        if quote is None and subset.startswith(b"<!--", i):
            end = subset.find(b"-->", i + 4)
            if end < 0:
                raise SecurityError(DTD_REJECTED_MESSAGE)
            i = end + 3
            continue
        if quote is None and ch in b"\"'":
            quote = ch
        elif ch == quote:
            quote = None
        out.append(ch)
        i += 1
    if quote is not None:
        raise SecurityError(DTD_REJECTED_MESSAGE)
    return bytes(out)


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
    subset = _strip_comments(match.group("subset") or b"")
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


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
# Globally routable by the registry but never a public web server: the old 6to4 relay anycast.
_EXTRA_BLOCKED = (ipaddress.ip_network("192.88.99.0/24"),)


def _ip_is_private(ip_text: str) -> bool:
    """True unless ``ip_text`` is a globally routable unicast address.

    An allowlist (``is_global``) instead of a list of private ranges: it also
    covers 100.64.0.0/10 (carrier-grade NAT, where some clouds put their
    metadata service), benchmarking and documentation ranges. IPv6 forms that
    embed an IPv4 address (mapped, 6to4, NAT64) are judged by that address.
    """
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True  # treat unparseable as unsafe
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
        elif ip in _NAT64:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if any(ip in net for net in _EXTRA_BLOCKED):
        return True
    return not ip.is_global or ip.is_multicast


def _resolve_all_addrs(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise SecurityError(f"DNS resolution failed for {host!r}: {exc}") from exc
    return list({info[4][0] for info in infos})


def _verify_url(url: str) -> tuple[str, list[str]]:
    """Validate ``url`` (scheme, host allowlist, no private IPs) and return
    ``(host, pinned_ips)``: the host's currently resolved public addresses,
    IPv4 first. The fetcher connects to *those* IPs, so a DNS answer that
    changes between this check and the connection (rebinding) cannot point the
    request at a private address."""
    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityError(f"only http(s) schemes are permitted; got {parsed.scheme!r}")
    host = parsed.host
    if not host:
        raise SecurityError(f"URL has no host: {url!r}")
    if parsed.userinfo:
        raise SecurityError("URLs with a user name or password are not supported")
    if not _host_is_allowed(host):
        raise SecurityError(
            f"host {host!r} is not on ALLOWED_SCHEMA_HOSTS lockdown whitelist"
        )
    addrs = _resolve_all_addrs(host)
    for addr in addrs:
        if _ip_is_private(addr):
            raise SecurityError(
                f"host {host!r} resolves to a private/loopback address ({addr}); refusing to fetch"
            )
    if not addrs:
        raise SecurityError(f"host {host!r} did not resolve to any address")
    addrs.sort(key=lambda a: ":" in a)
    return host, addrs


def _read_capped(response: httpx.Response, deadline: float) -> bytes:
    """Read a streamed body, aborting at the size cap (before it is all in
    memory) or at ``deadline`` (a server dripping bytes resets httpx's
    per-read timeout forever)."""
    cap = settings.fetch_max_response_bytes
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > cap:
            raise SecurityError(f"response exceeds {settings.fetch_max_response_mb} MB cap")
        if time.monotonic() > deadline:
            raise FetchError("the server is too slow; giving up")
        chunks.append(chunk)
    return b"".join(chunks)


def _http_failure_message(url: str, status_code: int) -> str:
    phrase = httpx.codes.get_reason_phrase(status_code)
    message = f"fetching {url!r} failed with HTTP {status_code} {phrase}".rstrip()
    if status_code == 403:
        message += " — the server refuses automated downloads; download the file and upload it here instead"
    return message


def fetch_schema_url(url: str) -> FetchedResource:
    """Fetch a schema document by URL, enforcing all SSRF mitigations.

    GitHub/GitLab/Bitbucket *browse* URLs are rewritten to their raw-content
    form first (see ``urls.normalize_schema_url``).
    """
    url = normalize_schema_url(url)
    remaining_redirects = settings.fetch_max_redirects
    current = url
    deadline = time.monotonic() + settings.fetch_deadline_seconds
    with httpx.Client(
        follow_redirects=False,
        timeout=settings.fetch_timeout_seconds,
        limits=httpx.Limits(max_connections=4),
        headers=FETCH_HEADERS,
    ) as client:
        while True:
            host, pinned_ips = _verify_url(current)
            parsed = httpx.URL(current)
            # Connect to the validated IPs (the next one on a connect failure),
            # keeping the Host header and TLS SNI / certificate check on the name.
            stream = None
            for i, pinned_ip in enumerate(pinned_ips):
                stream = client.stream(
                    "GET",
                    parsed.copy_with(host=pinned_ip),
                    headers={"Host": parsed.netloc.decode("ascii")},
                    extensions={"sni_hostname": host},
                )
                try:
                    response = stream.__enter__()
                    break
                except httpx.ConnectError as exc:
                    if i == len(pinned_ips) - 1:
                        raise FetchError(f"fetching {current!r} failed: {exc}") from exc
                except httpx.HTTPError as exc:
                    raise FetchError(f"fetching {current!r} failed: {exc}") from exc
            assert stream is not None
            try:
                if response.is_redirect:
                    if remaining_redirects <= 0:
                        raise SecurityError("too many HTTP redirects")
                    remaining_redirects -= 1
                    target = response.headers.get("location")
                    if not target:
                        raise SecurityError("redirect without Location header")
                    current = str(httpx.URL(current).join(target))
                    continue
                if response.status_code >= 400:
                    raise FetchError(_http_failure_message(current, response.status_code))
                try:
                    content = _read_capped(response, deadline)
                except httpx.HTTPError as exc:
                    raise FetchError(f"fetching {current!r} failed: {exc}") from exc
                content_type = response.headers.get("content-type")
            finally:
                stream.__exit__(None, None, None)
            logger.info(
                "fetched remote schema",
                extra={
                    "ctx_url": current,
                    "ctx_size_bytes": len(content),
                    "ctx_content_type": content_type,
                },
            )
            return FetchedResource(url=current, content=content, content_type=content_type)
