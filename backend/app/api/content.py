"""Content the SPA shares with the server-rendered pages, so it has one source.

Rate-limited like the other API routes (this site has no separate read limit)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.content.pages import home_faq
from app.content.render import markdown
from app.rate_limit import WRITE_LIMIT, limiter

router = APIRouter(tags=["content"])


class FaqEntry(BaseModel):
    question: str
    answer_html: str


@router.get("/content/faq", response_model=list[FaqEntry])
@limiter.limit(WRITE_LIMIT)
async def faq(request: Request) -> list[FaqEntry]:
    return [FaqEntry(question=item.question, answer_html=markdown(item.answer)) for item in home_faq()]
