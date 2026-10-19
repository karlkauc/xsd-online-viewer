"""Serve the built SPA: static assets plus the HTML shell for known client routes.

The shell is returned only for paths the frontend router actually knows
(mirrored from frontend/src/lib/modeRoute.ts). Everything else gets a plain
404 so vulnerability scanners probing /wp-login.php, /xleet.php, … neither
receive a 200 nor pollute the usage stats with fake page views.

Content pages (``app.content``) are plain HTML documents rendered here too;
``/sitemap.xml`` lists both kinds, and the home FAQ is filled into the shell.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.content.pages import all_pages, get_page, home_faq
from app.content.render import faq_html, faq_script, render_page, render_sitemap
from app.usage.context import emit
from app.usage.events import utm_fields

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
    # Kept out of search results and the sitemap (the iframe-only /embed view).
    noindex: bool = False


_HOME_DESCRIPTION = (
    "Free online XSD viewer: upload an XML Schema and explore it as a tree, "
    "XMLSpy-style diagram or highlighted source. Validate XML documents "
    "against the schema in the browser or via REST API."
)

# Keep in sync with MODE_TO_PATH / API_DOCS_* in frontend/src/lib/modeRoute.ts.
# Deep links to schema nodes use the URL hash, which never reaches the server.
ROUTE_META: dict[str, RouteMeta] = {
    "": RouteMeta(
        "XSD Viewer Online – XML Schema Diagram, Tree & Validator (Free)", _HOME_DESCRIPTION, "/"
    ),
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
    "iso20022": RouteMeta(
        "ISO 20022 XSD viewer: pain, camt, pacs schemas — Online XSD Viewer",
        "Open any ISO 20022 message schema — pain.001, pain.002, camt.053, camt.054, pacs.008 and 300 more, "
        "every version — as a tree or XMLSpy-style diagram, search it and validate XML files against it.",
        "/iso20022",
    ),
    "api-docs": RouteMeta(
        "XML validation via API (curl, PowerShell, Python) — Online XSD Viewer",
        "Validate XML against an XSD from the command line: upload the schema, validate the "
        "document, save the JSON error report. Examples for curl, PowerShell and Python, "
        "plus size, timeout and rate limits.",
        "/api-docs",
    ),
    "embed": RouteMeta(
        "Embedded schema diagram — Online XSD Viewer",
        "An XML Schema diagram embedded from the Online XSD Viewer.",
        "/",
        noindex=True,
    ),
}

SPA_ROUTES: frozenset[str] = frozenset(ROUTE_META)
# Routes other sites may show in an iframe; every other page keeps frame-ancestors 'none'.
EMBEDDABLE_ROUTES: frozenset[str] = frozenset({"embed"})

_TITLE_RE = re.compile(r"<title>.*?</title>", re.S)
_DESCRIPTION_RE = re.compile(r'(<meta\s+name="description"\s+content=")[^"]*(")', re.S)
_CANONICAL_RE = re.compile(r'(<link\s+rel="canonical"\s+href=")[^"]*(")', re.S)
_OG_RE = {
    key: re.compile(rf'(<meta\s+property="og:{key}"\s+content=")[^"]*(")', re.S)
    for key in ("title", "description", "url")
}


_FAQ_MARKER = "<!--faq-->"
_FAQ_JSONLD_MARKER = "<!--faq-jsonld-->"


def _shared_schema_name(src: str | None) -> str | None:
    """File name of a shared ``/url?src=`` schema, for the link preview; nothing is fetched."""
    if not src or not re.match(r"https?://", src, re.I):
        return None
    name = urlsplit(src).path.rstrip("/").rsplit("/", 1)[-1]
    name = unquote(name)[:80]
    return name or None


def render_shell(shell: str, route: str, src: str | None = None) -> str:
    """Return the index.html shell with title/description/canonical/OG for ``route``.

    A shared ``/url?src=…`` link gets the schema's file name in og:title and
    og:description, so a link pasted into Slack or Teams says what it opens.
    The <title> and canonical stay generic: the page is still the URL tab.
    """
    route = route.rstrip("/")
    meta = ROUTE_META[route]
    canonical = SITE_ORIGIN + meta.canonical
    title, description = html.escape(meta.title), html.escape(meta.description)
    og_title, og_description = title, description
    shared = _shared_schema_name(src) if route == "url" else None
    if shared:
        og_title = html.escape(f"{shared} — XML Schema in the Online XSD Viewer")
        og_description = html.escape(
            f"Explore {shared} as a tree, XMLSpy-style diagram and highlighted source, "
            "and validate XML documents against it — in the browser, no install."
        )
    shell = _TITLE_RE.sub(f"<title>{title}</title>", shell, count=1)
    shell = _DESCRIPTION_RE.sub(rf"\g<1>{description}\g<2>", shell, count=1)
    shell = _CANONICAL_RE.sub(rf"\g<1>{canonical}\g<2>", shell, count=1)
    for key, value in (("title", og_title), ("description", og_description), ("url", canonical)):
        shell = _OG_RE[key].sub(rf"\g<1>{value}\g<2>", shell, count=1)
    if meta.noindex:
        shell = shell.replace("</head>", '<meta name="robots" content="noindex" />\n</head>', 1)
    # FAQPage markup belongs to one URL only; the other routes just drop the markers.
    faq = home_faq() if route == "" else ()
    shell = shell.replace(_FAQ_MARKER, faq_html(faq), 1)
    return shell.replace(_FAQ_JSONLD_MARKER, faq_script(faq), 1)


def sitemap_urls() -> list[tuple[str, str | None]]:
    """Indexable URLs: the SPA routes with their own canonical, then every content page."""
    urls: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for meta in ROUTE_META.values():
        if not meta.noindex and meta.canonical not in seen:
            seen.add(meta.canonical)
            urls.append((SITE_ORIGIN + meta.canonical, None))
    for page in all_pages().values():
        if not page.noindex:
            urls.append((f"{SITE_ORIGIN}/{page.slug}", page.lastmod))
    return urls

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    # Nothing on the page needs these; closing them limits what injected markup could do.
    "base-uri 'self'; form-action 'self'; object-src 'none'; frame-ancestors 'none'"
)


def is_spa_route(full_path: str) -> bool:
    """True if the path (without leading slash) is a client-side route.

    A trailing slash is tolerated (/fundsxml/), nothing else is normalised.
    """
    return full_path.rstrip("/") in SPA_ROUTES


SHELL_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}

# /embed is meant to be framed by documentation sites: any ancestor, and no
# X-Frame-Options (DENY would win over the CSP in older browsers).
EMBED_HEADERS = {
    **{k: v for k, v in SHELL_HEADERS.items() if k != "X-Frame-Options"},
    "Content-Security-Policy": CSP.replace("frame-ancestors 'none'", "frame-ancestors *"),
}


def mount_spa(app: FastAPI, static_path: Path) -> None:
    app.mount("/assets", StaticFiles(directory=static_path / "assets"), name="assets")
    static_root = static_path.resolve()
    index_file = static_path / "index.html"

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap() -> Response:
        return Response(render_sitemap(sitemap_urls()), media_type="application/xml")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str, request: Request) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not_found"})
        # Serve root-level static files (favicon.svg, robots.txt, …) directly
        # instead of returning the SPA shell. Guarded against path traversal.
        if full_path and full_path != "index.html":
            candidate = (static_path / full_path).resolve()
            if static_root in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
        # IndexNow proves domain ownership with a key file at the root.
        if settings.indexnow_key and full_path == f"{settings.indexnow_key}.txt":
            return Response(settings.indexnow_key, media_type="text/plain")
        utm = utm_fields(request.query_params)
        page = get_page(full_path.rstrip("/")) if full_path.rstrip("/") else None
        if page is not None:
            emit("page_view", path="/" + full_path.rstrip("/"), status_code=200, **utm)
            return Response(
                content=render_page(page, SITE_ORIGIN), media_type="text/html", headers=SHELL_HEADERS
            )
        if not is_spa_route(full_path):
            return Response(status_code=404, content="Not Found", media_type="text/plain")
        route = full_path.rstrip("/")
        embed = route in EMBEDDABLE_ROUTES
        extra = {"source": "embed"} if embed else {}
        emit("page_view", path="/" + full_path, status_code=200, **extra, **utm)
        return Response(
            content=render_shell(
                index_file.read_text(encoding="utf-8"), full_path, request.query_params.get("src")
            ),
            media_type="text/html",
            headers=EMBED_HEADERS if embed else SHELL_HEADERS,
        )
