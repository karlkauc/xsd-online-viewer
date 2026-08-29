"""Serve the built SPA: static assets plus the HTML shell for known client routes.

The shell is returned only for paths the frontend router actually knows
(mirrored from frontend/src/lib/modeRoute.ts). Everything else gets a plain
404 so vulnerability scanners probing /wp-login.php, /xleet.php, … neither
receive a 200 nor pollute the usage stats with fake page views.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.usage.context import emit

SITE_ORIGIN = "https://www.xsd-viewer.online"


@dataclass(frozen=True)
class RouteMeta:
    """Per-route <head> metadata injected into the SPA shell.

    Search engines see the shell before any JavaScript runs, so title,
    description and canonical must already be correct in the served HTML;
    otherwise every route looks like a duplicate of "/".
    """

    title: str
    description: str
    # Canonical path. Input modes that are merely tabs of the same uploader
    # (/paste, /url) point at "/" so they are not indexed as duplicates.
    canonical: str


_HOME_DESCRIPTION = (
    "Free online XSD viewer: upload an XML Schema and explore it as a tree, "
    "XMLSpy-style diagram or highlighted source. Validate XML documents "
    "against the schema in the browser or via REST API."
)

# Keep in sync with MODE_TO_PATH / API_DOCS_* in frontend/src/lib/modeRoute.ts.
# Deep links to schema nodes use the URL hash, which never reaches the server.
ROUTE_META: dict[str, RouteMeta] = {
    "": RouteMeta("Online XSD Viewer", _HOME_DESCRIPTION, "/"),
    "paste": RouteMeta(
        "Paste an XSD — Online XSD Viewer",
        "Paste XML Schema source and view it as a tree, diagram or highlighted text. "
        + _HOME_DESCRIPTION,
        "/",
    ),
    "url": RouteMeta(
        "Load an XSD from a URL — Online XSD Viewer",
        "Load an XML Schema from a public URL and view it as a tree, diagram or highlighted text. "
        + _HOME_DESCRIPTION,
        "/",
    ),
    "fundsxml": RouteMeta(
        "FundsXML schema viewer — Online XSD Viewer",
        "Browse the official FundsXML 4.x schema releases online: explore FundsXML elements "
        "and types as a tree or XMLSpy-style diagram and validate FundsXML documents.",
        "/fundsxml",
    ),
    "api-docs": RouteMeta(
        "XML validation via API (curl, PowerShell, Python) — Online XSD Viewer",
        "Validate XML against an XSD from the command line: upload the schema, validate the "
        "document, save the JSON error report. Examples for curl, PowerShell and Python, "
        "plus size, timeout and rate limits.",
        "/api-docs",
    ),
}

SPA_ROUTES: frozenset[str] = frozenset(ROUTE_META)

_TITLE_RE = re.compile(r"<title>.*?</title>", re.S)
_DESCRIPTION_RE = re.compile(r'(<meta\s+name="description"\s+content=")[^"]*(")', re.S)
_CANONICAL_RE = re.compile(r'(<link\s+rel="canonical"\s+href=")[^"]*(")', re.S)
_OG_RE = {
    key: re.compile(rf'(<meta\s+property="og:{key}"\s+content=")[^"]*(")', re.S)
    for key in ("title", "description", "url")
}


def render_shell(shell: str, route: str) -> str:
    """Return the index.html shell with title/description/canonical/OG for ``route``."""
    meta = ROUTE_META[route.rstrip("/")]
    canonical = SITE_ORIGIN + meta.canonical
    title, description = html.escape(meta.title), html.escape(meta.description)
    shell = _TITLE_RE.sub(f"<title>{title}</title>", shell, count=1)
    shell = _DESCRIPTION_RE.sub(rf"\g<1>{description}\g<2>", shell, count=1)
    shell = _CANONICAL_RE.sub(rf"\g<1>{canonical}\g<2>", shell, count=1)
    for key, value in (("title", title), ("description", description), ("url", canonical)):
        shell = _OG_RE[key].sub(rf"\g<1>{value}\g<2>", shell, count=1)
    return shell

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'"
)


def is_spa_route(full_path: str) -> bool:
    """True if the path (without leading slash) is a client-side route.

    A trailing slash is tolerated (/fundsxml/), nothing else is normalised.
    """
    return full_path.rstrip("/") in SPA_ROUTES


def mount_spa(app: FastAPI, static_path: Path) -> None:
    app.mount("/assets", StaticFiles(directory=static_path / "assets"), name="assets")
    static_root = static_path.resolve()
    index_file = static_path / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not_found"})
        # Serve root-level static files (favicon.svg, robots.txt, …) directly
        # instead of returning the SPA shell. Guarded against path traversal.
        if full_path and full_path != "index.html":
            candidate = (static_path / full_path).resolve()
            if static_root in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
        if not is_spa_route(full_path):
            return Response(status_code=404, content="Not Found", media_type="text/plain")
        emit("page_view", path="/" + full_path, status_code=200)
        return Response(
            content=render_shell(index_file.read_text(encoding="utf-8"), full_path),
            media_type="text/html",
            headers={
                "Content-Security-Policy": CSP,
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )
