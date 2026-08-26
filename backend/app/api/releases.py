"""FundsXML releases listing endpoint.

Queries the GitHub REST API for published releases of the public
``fundsxml/schema`` repository, filters the assets down to XSD files, and
returns a cached, lightly-shaped JSON payload for the frontend upload page.

GitHub's unauthenticated rate limit is 60 req/h per IP. The response is
cached in-memory for ``_CACHE_TTL`` seconds; on upstream error the last
known-good response is served (stale-while-error) if available.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.schema import SchemaResponse, ingest_schema
from app.parser.security import SecurityError, fetch_schema_url
from app.parser.xsd_parser import parse_files_map
from app.rate_limit import WRITE_LIMIT, limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["releases"])

GITHUB_RELEASES_URL = "https://api.github.com/repos/fundsxml/schema/releases"
_REQUEST_TIMEOUT = 10.0
_MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # defensive cap on the GitHub response
_CACHE_TTL = 600  # seconds


class FundsXmlAsset(BaseModel):
    filename: str
    download_url: str
    size: int
    content_type: str | None = None


class FundsXmlRelease(BaseModel):
    tag_name: str
    name: str | None = None
    published_at: datetime
    prerelease: bool
    html_url: str
    assets: list[FundsXmlAsset]


class FundsXmlReleasesResponse(BaseModel):
    releases: list[FundsXmlRelease]
    cached_at: datetime
    ttl_seconds: int


_cache_lock = asyncio.Lock()
_cached_response: FundsXmlReleasesResponse | None = None
_cached_at_monotonic: float = 0.0


def _reset_cache_for_tests() -> None:
    """Drop the cached response. Exposed purely so tests can isolate runs."""
    global _cached_response, _cached_at_monotonic
    _cached_response = None
    _cached_at_monotonic = 0.0


def _shape_releases(payload: list[dict]) -> list[FundsXmlRelease]:
    releases: list[FundsXmlRelease] = []
    for raw in payload:
        if raw.get("draft"):
            continue
        xsd_assets = [
            FundsXmlAsset(
                filename=a["name"],
                download_url=a["browser_download_url"],
                size=int(a.get("size") or 0),
                content_type=a.get("content_type"),
            )
            for a in raw.get("assets", [])
            if isinstance(a.get("name"), str) and a["name"].lower().endswith(".xsd")
        ]
        if not xsd_assets:
            continue
        releases.append(
            FundsXmlRelease(
                tag_name=raw.get("tag_name") or "",
                name=raw.get("name"),
                published_at=raw["published_at"],
                prerelease=bool(raw.get("prerelease")),
                html_url=raw.get("html_url") or "",
                assets=xsd_assets,
            )
        )
    releases.sort(key=lambda r: r.published_at, reverse=True)
    return releases


async def _fetch_github_releases() -> list[dict]:
    """Call the GitHub REST API. Raises HTTPException on failure."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "online-xsd-viewer",
    }
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(
                GITHUB_RELEASES_URL, headers=headers, params={"per_page": 100}
            )
    except httpx.TimeoutException as exc:
        logger.warning("GitHub releases request timed out", extra={"ctx_error": str(exc)})
        raise HTTPException(status_code=504, detail="GitHub API request timed out") from exc
    except httpx.HTTPError as exc:
        logger.warning("GitHub releases request failed", extra={"ctx_error": str(exc)})
        raise HTTPException(status_code=502, detail="GitHub API unreachable") from exc

    if response.status_code == 403 and "rate limit" in response.text.lower():
        reset = response.headers.get("X-RateLimit-Reset")
        retry_after = response.headers.get("Retry-After") or reset or "60"
        raise HTTPException(
            status_code=503,
            detail="GitHub API rate limit exceeded; try again later",
            headers={"Retry-After": str(retry_after)},
        )
    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="GitHub API unavailable")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API returned HTTP {response.status_code}",
        )

    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise HTTPException(status_code=502, detail="GitHub API response too large")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="GitHub API returned invalid JSON") from exc
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="GitHub API returned unexpected shape")
    return data


class LoadReleasePayload(BaseModel):
    main_filename: str


@router.get("/fundsxml/releases", response_model=FundsXmlReleasesResponse)
async def list_fundsxml_releases() -> FundsXmlReleasesResponse:
    """Return the cached list of FundsXML releases with XSD assets."""
    global _cached_response, _cached_at_monotonic

    loop_now = asyncio.get_running_loop().time()
    if _cached_response is not None and (loop_now - _cached_at_monotonic) < _CACHE_TTL:
        return _cached_response

    async with _cache_lock:
        loop_now = asyncio.get_running_loop().time()
        if _cached_response is not None and (loop_now - _cached_at_monotonic) < _CACHE_TTL:
            return _cached_response

        try:
            raw = await _fetch_github_releases()
        except HTTPException:
            if _cached_response is not None:
                logger.info("serving stale FundsXML releases cache after upstream error")
                return _cached_response
            raise

        releases = _shape_releases(raw)
        response = FundsXmlReleasesResponse(
            releases=releases,
            cached_at=datetime.now(timezone.utc),  # noqa: UP017
            ttl_seconds=_CACHE_TTL,
        )
        _cached_response = response
        _cached_at_monotonic = asyncio.get_running_loop().time()
        logger.info(
            "cached FundsXML releases",
            extra={"ctx_release_count": len(releases)},
        )
        return response


@router.post(
    "/fundsxml/releases/{tag}/load",
    response_model=SchemaResponse,
)
@limiter.limit(WRITE_LIMIT)
async def load_release_schema(
    request: Request, tag: str, payload: LoadReleasePayload
) -> SchemaResponse:
    """Parse a release's main XSD with every sibling XSD asset pre-fetched.

    GitHub serves release assets from signed UUID-based URLs, so relative
    ``schemaLocation`` references cannot be resolved by plain ``urljoin``
    against the main asset's URL. This endpoint downloads every XSD asset
    of the release upfront and feeds them to the parser as a ZIP-style
    in-memory file set, keyed by filename, so filename-based imports like
    ``<xs:import schemaLocation="xmldsig-core-schema.xsd"/>`` resolve.
    """
    cached = await list_fundsxml_releases()
    release = next((r for r in cached.releases if r.tag_name == tag), None)
    if release is None:
        raise HTTPException(status_code=404, detail=f"release {tag!r} not found")

    main_asset = next(
        (a for a in release.assets if a.filename == payload.main_filename), None
    )
    if main_asset is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"asset {payload.main_filename!r} not found in release {tag!r}"
            ),
        )

    files: dict[str, bytes] = {}
    for asset in release.assets:
        try:
            fetched = await asyncio.to_thread(fetch_schema_url, asset.download_url)
        except SecurityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        files[asset.filename] = fetched.content

    return ingest_schema(
        source="release",
        schema_name=f"{tag}/{payload.main_filename}",
        input_bytes=sum(len(content) for content in files.values()),
        parse=lambda: parse_files_map(files, main_filename=payload.main_filename),
    )
