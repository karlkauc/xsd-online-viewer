"""Rate-limiter shared across API routers.

In-memory storage is used (single-container deployment). When scaling out,
swap `storage_uri` to a redis URL.

Client IP is taken from the ASGI scope, which honors `X-Forwarded-For`
*only* if uvicorn was started with `--forwarded-allow-ips`. The Dockerfile
sets that flag so the reverse proxy's Forwarded-For is trusted.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

WRITE_LIMIT = "30/minute"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)
