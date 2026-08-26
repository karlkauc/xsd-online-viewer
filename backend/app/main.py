"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __version__
from app.api.export import router as export_router
from app.api.feedback import router as feedback_router
from app.api.releases import router as releases_router
from app.api.schema import router as schema_router
from app.config import settings
from app.logging_setup import configure_logging, new_request_id, request_id_var
from app.rate_limit import limiter
from app.usage.context import RequestUsage, UsageTracker, bind, emit, unbind
from app.usage.feedback import FeedbackStore
from app.usage.geoip import GeoIp
from app.usage.recorder import UsageRecorder

configure_logging(settings.log_level)
logger = logging.getLogger("app")


class BufferRequestBodyMiddleware:
    """Drain the entire request body before the app can respond.

    Why: when the app returns an error mid-upload (e.g. multipart parsing
    error or a ValueError from the XSD parser after reading the form),
    uvicorn closes the upstream TCP connection without consuming the rest
    of the body. A reverse proxy (Apache mod_proxy_http) that is still
    streaming the body upstream then logs AH01097 ("pass request body
    failed") and delivers 502 to the browser instead of the real 4xx.
    Buffering the body in the ASGI layer makes the body always fully
    received before any handler runs, so the proxy completes the transfer.
    """

    def __init__(self, app, buffered_methods: tuple[str, ...] = ("POST", "PUT", "PATCH")) -> None:
        self.app = app
        self.buffered_methods = buffered_methods

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in self.buffered_methods:
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] == "http.request":
                body = message.get("body")
                if body:
                    chunks.append(body)
                if not message.get("more_body", False):
                    break

        buffered = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


def build_usage_tracker() -> UsageTracker:
    """Usage statistics — inert unless USAGE_DB_URL is set (docs/USAGE_STATS.md)."""
    recorder = UsageRecorder(settings.usage_db_url, settings.usage_db_password)
    geoip = GeoIp(settings.geoip_db_path, settings.maxmind_license_key) if recorder.enabled else None
    if recorder.enabled and not settings.usage_hash_secret:
        logger.warning("USAGE_HASH_SECRET is empty; visitor hashes are only date-salted")
    return UsageTracker(recorder, geoip, settings.usage_hash_secret)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    tracker = build_usage_tracker()
    application.state.usage = tracker
    application.state.feedback = FeedbackStore(settings.usage_db_url, settings.usage_db_password)
    await tracker.start()
    try:
        yield
    finally:
        await tracker.stop()


app = FastAPI(
    title="Online XSD/XML Viewer",
    version=__version__,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "detail": f"limit: {exc.detail}"},
        headers={"Retry-After": "60"},
    )


app.add_middleware(SlowAPIMiddleware)
app.add_middleware(BufferRequestBodyMiddleware)

# Same-origin deployment: the SPA is served from the same host as the API,
# so no CORS is needed by default. Set CORS_ALLOW_ORIGINS (comma-separated)
# only if a foreign frontend should call the API.
if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def request_logging(request: Request, call_next):
    rid = new_request_id()
    token = request_id_var.set(rid)
    tracker: UsageTracker | None = getattr(request.app.state, "usage", None)
    usage: RequestUsage | None = (
        RequestUsage(
            tracker=tracker,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referrer=request.headers.get("referer"),
        )
        if tracker is not None
        else None
    )
    usage_token = bind(usage)
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
        unbind(usage_token)
    if usage is not None and usage.emitted:
        # Cloud Run throttles CPU after the response; give the writer a bounded
        # chance to finish while we still have it (see docs/USAGE_STATS.md).
        await usage.tracker.recorder.drain(timeout=settings.usage_drain_seconds)
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
app.include_router(releases_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")

# --- Static frontend ------------------------------------------------------
# Serves the built React SPA. In dev, the Vite dev-server runs separately and
# proxies /api; in production the Docker image copies the built assets to
# settings.static_dir and FastAPI serves them here.
_static_path = Path(settings.static_dir)
if _static_path.is_dir() and (_static_path / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_static_path / "assets"), name="assets")

    _static_root = _static_path.resolve()

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not_found"})
        # Serve root-level static files (favicon.svg, robots.txt, …) directly
        # instead of returning the SPA shell. Guarded against path traversal.
        if full_path and full_path != "index.html":
            candidate = (_static_path / full_path).resolve()
            if (
                _static_root in candidate.parents
                and candidate.is_file()
            ):
                return FileResponse(candidate)
        index_file = _static_path / "index.html"
        emit("page_view", path="/" + full_path, status_code=200)
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
