"""Outbound links that should be counted: ``/go/<name>`` redirects.

The site promotes FreeXmlToolkit, the author's desktop app. The frontend
links to this same-origin route instead of the external URL so each click
becomes a ``page_view`` row with ``path=/go/<name>/<target>`` and ``source=<name>`` —
no client-side tracking, no new event type.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.usage.context import emit

router = APIRouter(tags=["go"])

FREEXMLTOOLKIT_TARGETS: dict[str, str] = {
    "docs": "https://karlkauc.github.io/FreeXmlToolkit/",
    "releases": "https://github.com/karlkauc/FreeXmlToolkit/releases",
}


@router.get("/go/freexmltoolkit", include_in_schema=False)
async def go_freexmltoolkit(to: str = Query("docs")) -> RedirectResponse:
    key = to if to in FREEXMLTOOLKIT_TARGETS else "docs"
    # The target rides in the path so the dashboard can tell Download
    # (releases) from Learn more (docs) apart.
    emit("page_view", path=f"/go/freexmltoolkit/{key}", source="freexmltoolkit", status_code=302)
    return RedirectResponse(FREEXMLTOOLKIT_TARGETS[key], status_code=302)
