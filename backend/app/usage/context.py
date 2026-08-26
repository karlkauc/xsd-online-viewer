"""Per-request usage context and the ``emit()`` helper used by routers.

The middleware in ``app.main`` stores a ``RequestUsage`` in a ContextVar;
route handlers call ``emit("schema_load", ...)`` without caring whether
statistics are enabled — with no tracker installed the call is a no-op.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from typing import Any

from app import __version__
from app.usage.events import (
    UsageEvent,
    classify_device,
    clean_referrer,
    truncate,
    visitor_hash,
)
from app.usage.geoip import GeoIp
from app.usage.recorder import UsageRecorder


class UsageTracker:
    """Bundles recorder + geoip + hashing secret; lives on ``app.state.usage``."""

    def __init__(self, recorder: UsageRecorder, geoip: GeoIp | None, hash_secret: str) -> None:
        self.recorder = recorder
        self.geoip = geoip
        self.hash_secret = hash_secret

    @property
    def enabled(self) -> bool:
        return self.recorder.enabled

    async def start(self) -> None:
        if not self.enabled:
            return
        await self.recorder.start()
        if self.geoip is not None:
            self.geoip.start()

    async def stop(self) -> None:
        await self.recorder.stop()
        if self.geoip is not None:
            self.geoip.close()


@dataclass(slots=True)
class RequestUsage:
    tracker: UsageTracker
    ip: str | None
    user_agent: str | None
    referrer: str | None
    emitted: bool = False


_request_usage: ContextVar[RequestUsage | None] = ContextVar("request_usage", default=None)


def bind(usage: RequestUsage | None):  # noqa: ANN201 - contextvars Token
    return _request_usage.set(usage)


def unbind(token) -> None:  # noqa: ANN001
    _request_usage.reset(token)


def current() -> RequestUsage | None:
    return _request_usage.get()


def _utc_today() -> date:
    return date(*time.gmtime()[:3])


def emit(event_type: str, **fields: Any) -> bool:
    """Build and enqueue an event for the current request. Never raises."""
    ctx = _request_usage.get()
    if ctx is None or not ctx.tracker.enabled:
        return False
    try:
        tracker = ctx.tracker
        event = UsageEvent(
            event_type=event_type,
            visitor_hash=visitor_hash(ctx.ip, ctx.user_agent, _utc_today(), tracker.hash_secret),
            country_code=tracker.geoip.country(ctx.ip) if tracker.geoip else None,
            user_agent=truncate(ctx.user_agent),
            device=classify_device(ctx.user_agent),
            app_version=__version__,
            referrer=clean_referrer(ctx.referrer),
            **fields,
        )
        if event.error_detail:
            event.error_detail = truncate(event.error_detail)
        accepted = tracker.recorder.record(event)
        ctx.emitted = ctx.emitted or accepted
        return accepted
    except Exception:  # noqa: BLE001 - statistics must never break a request
        return False
