"""Serve the built SPA: static assets plus the HTML shell for known client routes.

The shell is returned only for paths the frontend router actually knows
(mirrored from frontend/src/lib/modeRoute.ts). Everything else gets a plain
404 so vulnerability scanners probing /wp-login.php, /xleet.php, … neither
receive a 200 nor pollute the usage stats with fake page views.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.usage.context import emit

# Keep in sync with MODE_TO_PATH in frontend/src/lib/modeRoute.ts.
# Deep links to schema nodes use the URL hash, which never reaches the server.
SPA_ROUTES: frozenset[str] = frozenset({"", "paste", "url", "fundsxml", "api-docs"})

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
            content=index_file.read_bytes(),
            media_type="text/html",
            headers={
                "Content-Security-Policy": CSP,
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )
