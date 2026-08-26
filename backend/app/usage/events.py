"""Pure helpers for building usage events — no I/O, fully unit-testable."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, fields
from datetime import date
from urllib.parse import urlsplit, urlunsplit

MAX_TEXT = 255

_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|curl/|wget/|python-requests|python-httpx|aiohttp|go-http-client|"
    r"headless|lighthouse|preview|facebookexternalhit|scrapy|java/|libwww|okhttp|monitor|uptime",
    re.IGNORECASE,
)
_MOBILE_RE = re.compile(r"Mobile|Android|iPhone|iPad|iPod|Windows Phone|Opera Mini", re.IGNORECASE)


@dataclass(slots=True)
class UsageEvent:
    """One row of the ``usage_event`` table (column order = field order)."""

    event_type: str
    visitor_hash: str | None = None
    country_code: str | None = None
    user_agent: str | None = None
    device: str | None = None
    status_code: int | None = None
    app_version: str | None = None
    path: str | None = None
    referrer: str | None = None
    source: str | None = None
    schema_name: str | None = None
    target_namespace: str | None = None
    input_bytes: int | None = None
    file_count: int | None = None
    element_count: int | None = None
    type_count: int | None = None
    diagnostic_count: int | None = None
    error_count: int | None = None
    duration_ms: int | None = None
    status: str | None = None
    error_detail: str | None = None

    def as_row(self) -> tuple:
        return tuple(getattr(self, f.name) for f in fields(self))


COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(UsageEvent))

INSERT_SQL = (
    f"INSERT INTO usage_event ({', '.join(COLUMNS)}) VALUES ({', '.join('%s' for _ in COLUMNS)})"
)


def truncate(value: str | None, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:limit]


def visitor_hash(ip: str | None, user_agent: str | None, day: date, secret: str) -> str | None:
    """Daily-salted, non-reversible visitor id.

    The salt is HMAC(secret, day) — or just the day when no secret is set — so
    the same visitor hashes identically within one day and differently the
    next. Without ``secret`` a brute-force over the IPv4 space is feasible;
    ``USAGE_HASH_SECRET`` should therefore be set in production.
    """
    if not ip:
        return None
    day_key = day.isoformat()
    salt = hmac.new(secret.encode(), day_key.encode(), hashlib.sha256).hexdigest() if secret else day_key
    digest = hashlib.sha256(f"{salt}|{ip}|{user_agent or ''}".encode()).hexdigest()
    return digest[:32]


def classify_device(user_agent: str | None) -> str:
    if not user_agent or not user_agent.strip():
        return "unknown"
    if _BOT_RE.search(user_agent):
        return "bot"
    if _MOBILE_RE.search(user_agent):
        return "mobile"
    return "desktop"


def clean_referrer(header: str | None) -> str | None:
    """Keep scheme, host and path of a Referer; drop query, fragment, credentials."""
    if not header:
        return None
    try:
        parts = urlsplit(header.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
    return truncate(urlunsplit((parts.scheme, netloc, parts.path or "/", "", "")))


def schema_display_name(source: str, name: str | None) -> str | None:
    """What is stored as ``schema_name`` — never file content.

    upload/text: basename only; url: URL without query/fragment; release: as is.
    """
    if not name:
        return None
    if source == "url":
        try:
            parts = urlsplit(name)
        except ValueError:
            return truncate(name)
        return truncate(urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")))
    if source in ("upload", "text"):
        return truncate(re.split(r"[\\/]", name)[-1])
    return truncate(name)
