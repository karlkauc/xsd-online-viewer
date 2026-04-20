"""Schema upload / retrieval endpoints."""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.cache import schema_cache
from app.config import settings
from app.parser.model import SchemaModel
from app.parser.security import SecurityError, fetch_schema_url
from app.parser.xsd_parser import parse_with_url_fallback

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _read_upload(upload: UploadFile) -> bytes:
    max_bytes = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"upload exceeds {settings.max_upload_mb} MB limit",
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
async def upload_schema(
    request: Request,
    file: UploadFile,
    main_filename: Annotated[str | None, Form()] = None,
) -> SchemaResponse:
    """Accept a single .xsd file or a .zip archive."""
    content = await _read_upload(file)
    name = file.filename or "schema.xsd"
    try:
        if name.lower().endswith(".zip") or (file.content_type or "").endswith("zip"):
            model = parse_with_url_fallback(
                zip_bytes=content,
                main_filename=main_filename,
                main_bytes=None,
                base_url=None,
            )
        else:
            model = parse_with_url_fallback(
                zip_bytes=None,
                main_filename=name,
                main_bytes=content,
                base_url=None,
            )
    except (SecurityError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return finalize_schema_response(model)


@router.post("/schema/url", response_model=SchemaResponse)
async def load_schema_from_url(payload: UrlPayload) -> SchemaResponse:
    try:
        fetched = fetch_schema_url(payload.url)
    except SecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        model = parse_with_url_fallback(
            zip_bytes=None,
            main_filename=fetched.url,
            main_bytes=fetched.content,
            base_url=fetched.url,
        )
    except (SecurityError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return finalize_schema_response(model)


@router.post("/schema/text", response_model=SchemaResponse)
async def load_schema_from_text(payload: TextPayload) -> SchemaResponse:
    data = payload.content.encode("utf-8")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"content exceeds {settings.max_upload_mb} MB limit",
        )
    try:
        model = parse_with_url_fallback(
            zip_bytes=None,
            main_filename=payload.filename,
            main_bytes=data,
            base_url=None,
        )
    except (SecurityError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return finalize_schema_response(model)


@router.get("/schema/{schema_id}", response_model=SchemaResponse)
async def get_cached_schema(schema_id: str) -> SchemaResponse:
    model = schema_cache.get(schema_id)
    if model is None:
        raise HTTPException(status_code=404, detail="schema not found or expired")
    return SchemaResponse(schema_id=schema_id, model=model)
