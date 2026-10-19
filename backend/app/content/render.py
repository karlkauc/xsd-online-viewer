"""Turn content pages into HTML documents, the home FAQ into shell markup, and all URLs into a sitemap."""

from __future__ import annotations

import html
import json
from pathlib import Path
from string import Template
from xml.sax.saxutils import escape as xml_escape

from markdown_it import MarkdownIt

from app.content import site
from app.content.pages import HUB_SLUG, FaqItem, Page

# Raw HTML stays off: page sources are ours, but escaping costs nothing and
# keeps a stray "<" in a guide from turning into markup.
_md = MarkdownIt("commonmark", {"html": False, "typographer": True}).enable(["table", "replacements"])
_TEMPLATE = Template((Path(__file__).with_name("template.html")).read_text("utf-8"))


def markdown(text: str) -> str:
    return _md.render(text)


def markdown_inline(text: str) -> str:
    return _md.renderInline(text)


def _json_ld(data: dict) -> str:
    # "</" inside a <script> block would end it early.
    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")


def faq_json_ld(items: tuple[FaqItem, ...]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item.question,
                "acceptedAnswer": {"@type": "Answer", "text": markdown_inline(item.answer)},
            }
            for item in items
        ],
    }


def faq_html(items: tuple[FaqItem, ...]) -> str:
    """``<details>`` list — works without JavaScript and is what crawlers index."""
    return "\n".join(
        f'<details class="faq"><summary>{html.escape(item.question)}</summary>'
        f"{markdown(item.answer)}</details>"
        for item in items
    )


def faq_script(items: tuple[FaqItem, ...]) -> str:
    if not items:
        return ""
    return f'<script type="application/ld+json">\n{_json_ld(faq_json_ld(items))}\n</script>'


def family_html() -> str:
    parts = []
    for key, label, href in site.FAMILY:
        if key == site.SELF:
            parts.append(f'<strong aria-current="page">{html.escape(label)}</strong>')
        else:
            parts.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
    return "Part of the FreeXmlToolkit family: " + " · ".join(parts)


def _trail(page: Page) -> list[tuple[str, str]]:
    """Site › Guides › page; the hub itself sits directly below the site."""
    trail = [(site.SITE_NAME, "/")]
    if page.slug != HUB_SLUG:
        trail.append(("Guides", f"/{HUB_SLUG}"))
    return [*trail, (page.h1, f"/{page.slug}")]


def _crumbs_html(page: Page) -> str:
    *links, (current, _) = _trail(page)
    parts = [f'<a href="{html.escape(href)}">{html.escape(name)}</a>' for name, href in links]
    return " › ".join([*parts, f"<span>{html.escape(current)}</span>"])


def _breadcrumbs(page: Page, origin: str) -> dict:
    items = [
        {"@type": "ListItem", "position": i, "name": name, "item": origin + href}
        for i, (name, href) in enumerate(_trail(page), start=1)
    ]
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def render_page(page: Page, origin: str) -> str:
    url = f"{origin}/{page.slug}"
    article = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": page.h1,
        "description": page.description,
        "url": url,
        "isPartOf": {"@type": "WebSite", "name": site.SITE_NAME, "url": origin + "/"},
        "author": {"@type": "Person", "name": "Karl Kauc"},
    }
    if page.lastmod:
        article["dateModified"] = page.lastmod
    scripts = [_json_ld(article), _json_ld(_breadcrumbs(page, origin))]
    if page.faq:
        scripts.append(_json_ld(faq_json_ld(page.faq)))
    cta = ""
    if page.cta_href:
        cta = (
            f'<p class="cta"><a class="button" href="{html.escape(page.cta_href)}">'
            f"{html.escape(page.cta_label or 'Open in the viewer')}</a></p>"
        )
    faq = f'<section class="faq-list"><h2>Questions</h2>{faq_html(page.faq)}</section>' if page.faq else ""
    return _TEMPLATE.substitute(
        title=html.escape(f"{page.title} — {site.SITE_NAME}"),
        description=html.escape(page.description),
        canonical=html.escape(url),
        robots="noindex" if page.noindex else "index, follow",
        site_name=html.escape(site.SITE_NAME),
        logo=site.LOGO_PATH,
        viewer=site.VIEWER_PATH,
        json_ld="\n".join(f'<script type="application/ld+json">\n{s}\n</script>' for s in scripts),
        crumbs=_crumbs_html(page),
        h1=html.escape(page.h1),
        body=markdown(page.body),
        cta=cta,
        faq=faq,
        family=family_html(),
    )


def render_sitemap(urls: list[tuple[str, str | None]]) -> str:
    rows = []
    for loc, lastmod in urls:
        row = f"  <url><loc>{xml_escape(loc)}</loc>"
        if lastmod:
            row += f"<lastmod>{xml_escape(lastmod)}</lastmod>"
        rows.append(row + "</url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n"
    )
