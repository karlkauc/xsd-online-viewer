"""Client-reported usage events that have no request of their own on the server.

Copying a share link happens in the browser only; the button pings this
endpoint so the stats can count shares. No body, no identifiers beyond what
every event already carries.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from app.rate_limit import WRITE_LIMIT, limiter
from app.usage.context import emit

router = APIRouter(tags=["usage"])

# What the copied link loads: a schema URL (/url?src=), a FundsXML release or an ISO 20022 message.
SHARE_SOURCES = frozenset({"url", "fundsxml", "iso20022"})


@router.post("/usage/share", status_code=204, include_in_schema=False)
@limiter.limit(WRITE_LIMIT)
async def record_share(request: Request, source: str = Query("url", max_length=32)) -> Response:
    emit("share", source=source if source in SHARE_SOURCES else "other", status_code=204)
    return Response(status_code=204)
