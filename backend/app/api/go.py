"""Outbound links that should be counted: ``/go/<name>`` redirects.

The site promotes FreeXmlToolkit, the author's desktop app, and links to the
author's GitHub Sponsors page, and links the sister sites of the family. The
frontend links to these same-origin routes instead of the external URLs so each click
becomes a ``page_view`` row with ``path=/go/<name>/<target>`` and ``source=<name>`` —
no client-side tracking, no new event type.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.usage.context import emit

router = APIRouter(tags=["go"])

FREEXMLTOOLKIT_TARGETS: dict[str, str] = {
    "docs": "https://karlkauc.github.io/FreeXmlToolkit/",
    "releases": "https://github.com/karlkauc/FreeXmlToolkit/releases",
}

SPONSOR_URL = "https://github.com/sponsors/karlkauc"

# The sister sites. utm_source tells their stats where the visitor came from
# (the sites send no Referer). Keep the list identical on all sites of the family.
SITE_KEY = "xsd-viewer"
SISTER_URLS: dict[str, str] = {
    "xsd-viewer": "https://www.xsd-viewer.online/",
    "xml-viewer": "https://www.xml-viewer.online/",
    "odata-viewer": "https://www.odata-viewer.online/",
    "tpt-converter": "https://www.fund-data-converter.eu/",
}


@router.get("/go/freexmltoolkit", include_in_schema=False)
async def go_freexmltoolkit(to: str = Query("docs")) -> RedirectResponse:
    key = to if to in FREEXMLTOOLKIT_TARGETS else "docs"
    # The target rides in the path so the dashboard can tell Download
    # (releases) from Learn more (docs) apart.
    emit("page_view", path=f"/go/freexmltoolkit/{key}", source="freexmltoolkit", status_code=302)
    return RedirectResponse(FREEXMLTOOLKIT_TARGETS[key], status_code=302)


@router.get("/go/sponsor", include_in_schema=False)
async def go_sponsor() -> RedirectResponse:
    emit("page_view", path="/go/sponsor", source="sponsor", status_code=302)
    return RedirectResponse(SPONSOR_URL, status_code=302)


@router.get("/go/{sister}", include_in_schema=False)
async def go_sister(sister: str) -> Response:
    if sister not in SISTER_URLS:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    target = SISTER_URLS[sister]
    if sister != SITE_KEY:
        target += f"?utm_source={SITE_KEY}&utm_medium=sister"
    emit("page_view", path=f"/go/{sister}", source=sister, status_code=302)
    return RedirectResponse(target, status_code=302)
