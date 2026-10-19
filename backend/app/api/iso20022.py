"""ISO 20022 messages by name: the "ISO 20022" tab and /iso20022?message=… links.

iso20022.org refuses automated downloads, so the schemas come from a public
mirror pinned to one commit (``app/standards/iso20022_catalog.json``, written by
``tools/build_iso20022_catalog.py``). The client only names a message id; the
URL is built from the catalogue, never taken from the request.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.schema import SchemaResponse, ingest_schema, reject
from app.parser.security import SecurityError, fetch_schema_url
from app.parser.xsd_parser import parse_single
from app.rate_limit import WRITE_LIMIT, limiter

router = APIRouter(tags=["iso20022"])

CATALOG_FILE = Path(__file__).resolve().parent.parent / "standards" / "iso20022_catalog.json"


class Iso20022Source(BaseModel):
    repo: str
    commit: str
    license: str
    base_url: str
    official: str


class Iso20022Message(BaseModel):
    id: str  # pain.001.001.12
    message: str  # pain.001
    variant: str  # 001
    version: str  # 12
    area: str
    area_label: str
    name: str  # Customer Credit Transfer Initiation
    root: str  # CstmrCdtTrfInitn
    path: str


class Iso20022Catalog(BaseModel):
    source: Iso20022Source
    messages: list[Iso20022Message]


@lru_cache(maxsize=1)
def catalog() -> Iso20022Catalog:
    return Iso20022Catalog.model_validate(json.loads(CATALOG_FILE.read_text(encoding="utf-8")))


def message_url(message: Iso20022Message) -> str:
    return catalog().source.base_url + message.path


@router.get("/iso20022/messages", response_model=Iso20022Catalog)
async def list_messages() -> Iso20022Catalog:
    return catalog()


@router.post("/iso20022/{message_id}/load", response_model=SchemaResponse)
@limiter.limit(WRITE_LIMIT)
async def load_message(request: Request, message_id: str) -> SchemaResponse:
    message = next((m for m in catalog().messages if m.id == message_id), None)
    if message is None:
        raise reject("schema_load", "iso20022", 404, f"unknown ISO 20022 message {message_id!r}")
    try:
        fetched = await asyncio.to_thread(fetch_schema_url, message_url(message))
    except SecurityError as exc:
        raise reject("schema_load", "iso20022", 400, str(exc), schema_name=message.id) from exc
    return ingest_schema(
        source="iso20022",
        schema_name=message.id,
        input_bytes=len(fetched.content),
        parse=lambda: parse_single(fetched.content, f"{message.id}.xsd"),
    )
