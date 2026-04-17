"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.export import router as export_router
from app.api.schema import router as schema_router
from app.config import settings
from app.logging_setup import configure_logging, new_request_id, request_id_var

configure_logging(settings.log_level)
logger = logging.getLogger("app")

app = FastAPI(
    title="Online XSD/XML Viewer",
    version=__version__,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    rid = new_request_id()
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed",
            extra={"ctx_method": request.method, "ctx_path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "request_id": rid},
        )
    finally:
        request_id_var.reset(token)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request completed",
        extra={
            "ctx_method": request.method,
            "ctx_path": request.url.path,
            "ctx_status": response.status_code,
            "ctx_duration_ms": duration_ms,
        },
    )
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


app.include_router(schema_router, prefix="/api")
app.include_router(export_router, prefix="/api")

# --- Static frontend ------------------------------------------------------
# Serves the built React SPA. In dev, the Vite dev-server runs separately and
# proxies /api; in production the Docker image copies the built assets to
# settings.static_dir and FastAPI serves them here.
_static_path = Path(settings.static_dir)
if _static_path.is_dir() and (_static_path / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_static_path / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not_found"})
        index_file = _static_path / "index.html"
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'"
        )
        return Response(
            content=index_file.read_bytes(),
            media_type="text/html",
            headers={
                "Content-Security-Policy": csp,
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )
else:
    logger.info(
        "static assets not found; API-only mode",
        extra={"ctx_static_dir": str(_static_path)},
    )
