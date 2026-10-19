"""Rate-limiter shared across API routers.

In-memory storage is used (single-container deployment). When scaling out,
swap `storage_uri` to a redis URL.

The client IP comes from :func:`client_ip`: the `X-Forwarded-For` entry the
trusted proxy appended (Cloud Run's front end, Apache), counted from the right.
Entries further left are whatever the client sent and must never be trusted —
uvicorn's `--forwarded-allow-ips=*` picked the left-most one, so a made-up
header gave every request a fresh rate-limit key, visitor hash and country.
"""

from __future__ import annotations

from slowapi import Limiter
from starlette.requests import Request

from app.config import settings

WRITE_LIMIT = "30/minute"


def client_ip(request: Request) -> str | None:
    """The visitor's IP: the ``TRUSTED_PROXY_HOPS``-th X-Forwarded-For entry from the right."""
    hops = settings.trusted_proxy_hops
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
    forwarded = [part for part in forwarded if part]
    if hops > 0 and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.client.host if request.client else None


limiter = Limiter(
    key_func=lambda request: client_ip(request) or "unknown",
    default_limits=[],
)
