"""Export endpoints: HTML documentation and formatted XML.

PNG/SVG exports of the diagram are produced by the frontend (React Flow has
native ``toSvg`` / canvas rendering and keeps layout state client-side); the
backend therefore only offers an HTML-documentation export and a
pretty-printed source download.
"""

from __future__ import annotations

import html
import logging
from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from lxml import etree

from app.cache import schema_cache
from app.parser.model import (
    Annotation,
    ComplexType,
    ElementDecl,
    Facet,
    SchemaModel,
    SimpleType,
)
from app.parser.sample import SampleOptions, find_element, generate_sample
from app.usage.context import emit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


@router.get("/schema/{schema_id}/export/html", response_class=Response)
async def export_html(schema_id: str) -> Response:
    model = schema_cache.get(schema_id)
    if model is None:
        emit("export", source="html", status="rejected", status_code=404)
        raise HTTPException(status_code=404, detail="schema not found or expired")
    document = _render_html(model)
    emit("export", source="html", status="ok", status_code=200, file_count=len(model.files))
    return Response(
        content=document,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="schema-{schema_id}.html"'},
    )


@router.get("/schema/{schema_id}/sample", response_class=Response)
async def export_sample_xml(
    schema_id: str,
    element: str = Query(..., description="id of the element to use as document root"),
    optional: bool = Query(False, description="also emit optional elements and attributes"),
    repeat: int = Query(1, ge=1, le=5, description="occurrences for repeatable particles"),
    depth: int = Query(12, ge=1, le=30, description="maximum nesting depth"),
) -> Response:
    """A skeleton XML instance document for one element of the schema."""
    model = schema_cache.get(schema_id)
    if model is None:
        emit("export", source="sample", status="rejected", status_code=404)
        raise HTTPException(status_code=404, detail="schema not found or expired")
    declaration = find_element(model, element)
    if declaration is None:
        emit("export", source="sample", status="rejected", status_code=404)
        raise HTTPException(status_code=404, detail="element not found in schema")
    document = generate_sample(
        model, declaration, SampleOptions(include_optional=optional, repeat=repeat, max_depth=depth)
    )
    emit("export", source="sample", status="ok", status_code=200, file_count=len(model.files))
    name = (declaration.name or "sample").replace("/", "_")
    return Response(
        content=document,
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{name}-sample.xml"'},
    )


@router.get("/schema/{schema_id}/file/{file_id}/formatted", response_class=Response)
async def export_formatted_file(schema_id: str, file_id: str) -> Response:
    model = schema_cache.get(schema_id)
    if model is None:
        emit("export", source="formatted", status="rejected", status_code=404)
        raise HTTPException(status_code=404, detail="schema not found or expired")
    for source in model.files:
        if source.id == file_id and source.content is not None:
            pretty = _pretty_xml(source.content)
            filename = source.filename.split("/")[-1] or "schema.xsd"
            emit("export", source="formatted", status="ok", status_code=200)
            return Response(
                content=pretty,
                media_type="application/xml; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
    raise HTTPException(status_code=404, detail="file not found in schema")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pretty_xml(xml_text: str) -> str:
    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
    tree = etree.parse(BytesIO(xml_text.encode("utf-8")), parser)
    return etree.tostring(
        tree, pretty_print=True, encoding="UTF-8", xml_declaration=True
    ).decode("utf-8")


def _render_html(model: SchemaModel) -> str:
    parts: list[str] = []
    parts.append(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>XSD Schema Documentation</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;"
        "padding:0 1rem;line-height:1.5;color:#111}"
        "h1,h2,h3{color:#222}"
        "h2{border-bottom:1px solid #ddd;padding-bottom:.3rem;margin-top:2.5rem}"
        "code{background:#f4f4f4;padding:.1rem .3rem;border-radius:3px}"
        "table{border-collapse:collapse;margin:.5rem 0}"
        "th,td{border:1px solid #ddd;padding:.3rem .6rem;text-align:left}"
        "th{background:#f8f8f8}"
        ".doc{margin:.3rem 0;color:#444}"
        ".ann{background:#fff7e6;padding:.4rem .6rem;border-left:3px solid #f5a623;"
        "margin:.4rem 0;font-size:.9rem}"
        ".facets li{font-family:monospace;font-size:.9rem}"
        ".source{color:#888;font-size:.8rem}"
        "</style></head><body>"
    )
    parts.append("<h1>XSD Schema Documentation</h1>")
    if model.target_namespace:
        tns = html.escape(model.target_namespace)
        parts.append(f"<p><strong>Target namespace:</strong> <code>{tns}</code></p>")

    if model.files:
        parts.append("<h2>Files</h2><ul>")
        for source in model.files:
            filename = html.escape(source.filename)
            tns_suffix = (
                f" (targetNamespace={html.escape(source.target_namespace)})"
                if source.target_namespace
                else ""
            )
            parts.append(
                f"<li><code>{filename}</code> — {source.relationship}"
                f"{tns_suffix}</li>"
            )
        parts.append("</ul>")

    if model.elements:
        parts.append("<h2>Global Elements</h2>")
        for element in model.elements:
            parts.append(_render_element(element))

    if model.complex_types:
        parts.append("<h2>Complex Types</h2>")
        for complex_type in model.complex_types:
            parts.append(_render_complex_type(complex_type))

    if model.simple_types:
        parts.append("<h2>Simple Types</h2>")
        for simple_type in model.simple_types:
            parts.append(_render_simple_type(simple_type))

    if model.diagnostics:
        parts.append("<h2>Diagnostics</h2><ul>")
        for diagnostic in model.diagnostics:
            message = html.escape(diagnostic.message)
            parts.append(
                f"<li><strong>{diagnostic.severity}</strong>: {message}</li>"
            )
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def _render_annotation(annotation: Annotation | None) -> str:
    if annotation is None or annotation.is_empty:
        return ""
    parts: list[str] = []
    for doc in annotation.documentation:
        lang = f" ({doc.lang})" if doc.lang else ""
        parts.append(f"<div class='doc'>{html.escape(doc.text)}{lang}</div>")
    for comment in annotation.comments:
        parts.append(f"<div class='doc'><em>// {html.escape(comment.strip())}</em></div>")
    for app in annotation.appinfo:
        source = f" source={html.escape(app.source_uri)}" if app.source_uri else ""
        parts.append(f"<pre class='ann'>appinfo{source}\n{html.escape(app.raw_xml)}</pre>")
    return "".join(parts)


def _render_facets(facets: list[Facet]) -> str:
    if not facets:
        return ""
    items = "".join(
        f"<li>{html.escape(f.kind)} = <code>{html.escape(f.value)}</code>"
        f"{' (fixed)' if f.fixed else ''}</li>"
        for f in facets
    )
    return f"<ul class='facets'>{items}</ul>"


def _render_element(element: ElementDecl) -> str:
    name = element.name or element.ref or "(unnamed)"
    return (
        f"<h3 id='{html.escape(element.id)}'>"
        f"&lt;{html.escape(name)}&gt; "
        f"{'<small>(abstract)</small>' if element.abstract else ''}"
        "</h3>"
        + _render_annotation(element.annotation)
        + f"<p><strong>Type:</strong> <code>{html.escape(element.type_name or 'anonymous')}</code></p>"
    )


def _render_complex_type(complex_type: ComplexType) -> str:
    return (
        f"<h3 id='{html.escape(complex_type.id)}'>{html.escape(complex_type.name or '(anonymous)')}</h3>"
        + _render_annotation(complex_type.annotation)
        + (
            f"<p><strong>Derivation:</strong> {complex_type.derivation} of "
            f"<code>{html.escape(complex_type.base)}</code></p>"
            if complex_type.base
            else ""
        )
    )


def _render_simple_type(simple_type: SimpleType) -> str:
    return (
        f"<h3 id='{html.escape(simple_type.id)}'>{html.escape(simple_type.name or '(anonymous)')}</h3>"
        + _render_annotation(simple_type.annotation)
        + (
            f"<p><strong>Derivation:</strong> {simple_type.derivation}"
            + (f" of <code>{html.escape(simple_type.base)}</code>" if simple_type.base else "")
            + "</p>"
        )
        + _render_facets(simple_type.facets)
    )
