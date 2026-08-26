"""User feedback endpoint — stores messages in the usage-stats database."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import __version__
from app.rate_limit import limiter
from app.usage.context import current
from app.usage.events import classify_device, truncate, visitor_hash
from app.usage.feedback import FeedbackRow, FeedbackStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

FEEDBACK_LIMIT = "5/minute"
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class FeedbackPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    email: str | None = Field(default=None, max_length=254, pattern=_EMAIL_PATTERN)
    page: str | None = Field(default=None, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    error_detail: str | None = Field(default=None, max_length=255)
    # Honeypot: real users never see this field; bots that fill it are dropped silently.
    website: str | None = Field(default=None, max_length=255)


@router.post("/feedback", status_code=204)
@limiter.limit(FEEDBACK_LIMIT)
async def submit_feedback(request: Request, payload: FeedbackPayload) -> Response:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be empty")
    if payload.website:
        return Response(status_code=204)
    store: FeedbackStore | None = getattr(request.app.state, "feedback", None)
    if store is None or not store.enabled:
        raise HTTPException(status_code=503, detail="feedback is not configured on this server")

    ctx = current()
    ua = ctx.user_agent if ctx else request.headers.get("user-agent")
    ip = ctx.ip if ctx else (request.client.host if request.client else None)
    tracker = ctx.tracker if ctx else None
    row = FeedbackRow(
        message=message,
        email=(payload.email or "").strip() or None,
        page=truncate(payload.page),
        schema_name=truncate(payload.schema_name),
        error_detail=truncate(payload.error_detail),
        visitor_hash=visitor_hash(ip, ua, date.today(), tracker.hash_secret) if tracker else None,
        country_code=tracker.geoip.country(ip) if tracker and tracker.geoip else None,
        user_agent=truncate(ua),
        device=classify_device(ua),
        app_version=__version__,
    )
    try:
        await store.save(row)
    except Exception as exc:  # noqa: BLE001 - report honestly, never 500
        logger.warning("feedback insert failed: %r", exc)
        raise HTTPException(
            status_code=503, detail="could not store feedback, please try again later"
        ) from exc
    logger.info("feedback stored", extra={"ctx_page": row.page, "ctx_has_email": bool(row.email)})
    return Response(status_code=204)
