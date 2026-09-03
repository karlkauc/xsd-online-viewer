"""Schema upload / retrieval endpoints."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.cache import schema_cache
from app.config import settings
from app.parser.model import SchemaModel
from app.parser.security import SecurityError, fetch_schema_url
from app.parser.urls import html_response_message, looks_like_html
from app.parser.validation import (
    ValidationResponse,
    ValidationSetupError,
    validate_xml,
)
from app.parser.xsd_parser import parse_files_map, parse_with_url_fallback, pick_main_xsd
from app.rate_limit import WRITE_LIMIT, limiter
from app.usage.context import emit
from app.usage.events import schema_display_name, truncate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["schema"])


class UrlPayload(BaseModel):
    url: str = Field(..., description="Absolute http(s) URL of the XSD")


class TextPayload(BaseModel):
    filename: str = Field(default="schema.xsd")
    content: str = Field(..., description="Raw XSD content")


class SchemaResponse(BaseModel):
    schema_id: str
    model: SchemaModel


class ValidateTextPayload(BaseModel):
    content: str = Field(..., description="Raw XML content to validate")
    filename: str = Field(default="document.xml")


class ValidateUrlPayload(BaseModel):
    url: str = Field(..., description="Absolute http(s) URL of the XML document")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def reject(event_type: str, source: str, status_code: int, detail: str, **fields) -> HTTPException:
    """Record a rejected request (size limit, SSRF guard, expired cache) and build the HTTPException."""
    emit(event_type, source=source, status="rejected", status_code=status_code, error_detail=detail, **fields)
    return HTTPException(status_code=status_code, detail=detail)


def ingest_schema(
    *, source: str, schema_name: str | None, input_bytes: int, parse: Callable[[], SchemaModel]
) -> SchemaResponse:
    """Run a parser callable, cache the result and emit one ``schema_load`` usage event."""
    started = time.perf_counter()
    name = schema_display_name(source, schema_name)
    try:
        model = parse()
    except (SecurityError, ValueError) as exc:
        emit(
            "schema_load",
            source=source,
            schema_name=name,
            input_bytes=input_bytes,
            duration_ms=_ms(started),
            status="parse_error",
            status_code=400,
            error_detail=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = finalize_schema_response(model)
    emit(
        "schema_load",
        source=source,
        schema_name=name,
        target_namespace=truncate(model.target_namespace),
        input_bytes=input_bytes,
        file_count=len(model.files),
        element_count=len(model.elements),
        type_count=len(model.simple_types) + len(model.complex_types),
        diagnostic_count=len(model.diagnostics),
        duration_ms=_ms(started),
        status="ok",
        status_code=200,
    )
    return response


async def _read_upload(
    upload: UploadFile, *, event_type: str = "schema_load", source: str = "upload"
) -> bytes:
    max_bytes = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise reject(
                event_type,
                source,
                413,
                f"upload exceeds {settings.max_upload_mb} MB limit",
                schema_name=schema_display_name(source, upload.filename),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def finalize_schema_response(model: SchemaModel) -> SchemaResponse:
    payload = model.model_dump_json().encode("utf-8")
    schema_id = hashlib.sha256(payload).hexdigest()[:32]
    model.schema_id = schema_id
    schema_cache.put(schema_id, model)
    logger.info(
        "schema parsed",
        extra={
            "ctx_schema_id": schema_id,
            "ctx_files": len(model.files),
            "ctx_elements": len(model.elements),
            "ctx_types": len(model.simple_types) + len(model.complex_types),
            "ctx_diagnostics": len(model.diagnostics),
        },
    )
    return SchemaResponse(schema_id=schema_id, model=model)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/schema/upload", response_model=SchemaResponse)
@limiter.limit(WRITE_LIMIT)
async def upload_schema(
    request: Request,
    file: list[UploadFile],
    main_filename: Annotated[str | None, Form()] = None,
) -> SchemaResponse:
    """Accept a single .xsd file, a .zip archive, or several loose files.

    Several ``file`` parts are treated like the entries of one ZIP: they
    resolve each other's ``xs:include`` / ``xs:import`` by file name, and
    ``main_filename`` (or the usual shallowest/shortest heuristic) picks
    the root schema.
    """
    if len(file) > 1:
        files: dict[str, bytes] = {}
        total = 0
        for part in file:
            content = await _read_upload(part)
            total += len(content)
            if total > settings.max_upload_bytes:
                raise reject(
                    "schema_load",
                    "upload",
                    413,
                    f"uploads together exceed {settings.max_upload_mb} MB limit",
                    schema_name=schema_display_name("upload", main_filename),
                )
            files[part.filename or f"file{len(files) + 1}.xsd"] = content
        main = main_filename or pick_main_xsd(files) or next(iter(files))
        return ingest_schema(
            source="upload",
            schema_name=main,
            input_bytes=total,
            parse=lambda: parse_files_map(files, main),
        )

    single = file[0]
    content = await _read_upload(single)
    name = single.filename or "schema.xsd"
    if name.lower().endswith(".zip") or (single.content_type or "").endswith("zip"):
        return ingest_schema(
            source="upload",
            schema_name=main_filename or name,
            input_bytes=len(content),
            parse=lambda: parse_with_url_fallback(
                zip_bytes=content, main_filename=main_filename, main_bytes=None, base_url=None
            ),
        )
    return ingest_schema(
        source="upload",
        schema_name=name,
        input_bytes=len(content),
        parse=lambda: parse_with_url_fallback(
            zip_bytes=None, main_filename=name, main_bytes=content, base_url=None
        ),
    )


@router.post("/schema/url", response_model=SchemaResponse)
@limiter.limit(WRITE_LIMIT)
async def load_schema_from_url(request: Request, payload: UrlPayload) -> SchemaResponse:
    try:
        fetched = fetch_schema_url(payload.url)
    except SecurityError as exc:
        raise reject(
            "schema_load", "url", 400, str(exc), schema_name=schema_display_name("url", payload.url)
        ) from exc
    if looks_like_html(fetched.content, fetched.content_type):
        raise reject(
            "schema_load",
            "url",
            400,
            html_response_message(fetched.url),
            schema_name=schema_display_name("url", fetched.url),
        )

    return ingest_schema(
        source="url",
        schema_name=fetched.url,
        input_bytes=len(fetched.content),
        parse=lambda: parse_with_url_fallback(
            zip_bytes=None, main_filename=fetched.url, main_bytes=fetched.content, base_url=fetched.url
        ),
    )


@router.post("/schema/text", response_model=SchemaResponse)
@limiter.limit(WRITE_LIMIT)
async def load_schema_from_text(request: Request, payload: TextPayload) -> SchemaResponse:
    data = payload.content.encode("utf-8")
    if len(data) > settings.max_upload_bytes:
        raise reject(
            "schema_load",
            "text",
            413,
            f"content exceeds {settings.max_upload_mb} MB limit",
            schema_name=schema_display_name("text", payload.filename),
        )
    return ingest_schema(
        source="text",
        schema_name=payload.filename,
        input_bytes=len(data),
        parse=lambda: parse_with_url_fallback(
            zip_bytes=None, main_filename=payload.filename, main_bytes=data, base_url=None
        ),
    )


@router.get("/schema/{schema_id}", response_model=SchemaResponse)
async def get_cached_schema(schema_id: str) -> SchemaResponse:
    model = schema_cache.get(schema_id)
    if model is None:
        raise HTTPException(status_code=404, detail="schema not found or expired")
    return SchemaResponse(schema_id=schema_id, model=model)


# ---------------------------------------------------------------------------
# XML validation against a cached schema
# ---------------------------------------------------------------------------


def _validate_xml_against_schema(schema_id: str, xml_bytes: bytes, source: str) -> ValidationResponse:
    started = time.perf_counter()
    model = schema_cache.get(schema_id)
    if model is None:
        raise reject("validate", source, 404, "schema not found or expired", input_bytes=len(xml_bytes))
    try:
        result = validate_xml(model, xml_bytes)
    except ValidationSetupError as exc:
        raise reject("validate", source, 422, str(exc), input_bytes=len(xml_bytes)) from exc
    except SecurityError as exc:
        raise reject("validate", source, 400, str(exc), input_bytes=len(xml_bytes)) from exc
    emit(
        "validate",
        source=source,
        target_namespace=truncate(model.target_namespace),
        input_bytes=len(xml_bytes),
        error_count=len(result.errors),
        duration_ms=_ms(started),
        status="ok" if result.is_valid else "invalid",
        status_code=200,
    )
    return result


@router.post("/schema/{schema_id}/validate/upload", response_model=ValidationResponse)
@limiter.limit(WRITE_LIMIT)
async def validate_xml_upload(
    request: Request, schema_id: str, file: UploadFile
) -> ValidationResponse:
    content = await _read_upload(file, event_type="validate", source="upload")
    return _validate_xml_against_schema(schema_id, content, "upload")


@router.post("/schema/{schema_id}/validate/text", response_model=ValidationResponse)
@limiter.limit(WRITE_LIMIT)
async def validate_xml_text(
    request: Request, schema_id: str, payload: ValidateTextPayload
) -> ValidationResponse:
    data = payload.content.encode("utf-8")
    if len(data) > settings.max_upload_bytes:
        raise reject("validate", "text", 413, f"content exceeds {settings.max_upload_mb} MB limit")
    return _validate_xml_against_schema(schema_id, data, "text")


@router.post("/schema/{schema_id}/validate/url", response_model=ValidationResponse)
@limiter.limit(WRITE_LIMIT)
async def validate_xml_url(
    request: Request, schema_id: str, payload: ValidateUrlPayload
) -> ValidationResponse:
    try:
        fetched = fetch_schema_url(payload.url)
    except SecurityError as exc:
        raise reject("validate", "url", 400, str(exc)) from exc
    return _validate_xml_against_schema(schema_id, fetched.content, "url")
