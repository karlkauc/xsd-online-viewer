"""Server-rendered content pages, home FAQ, sitemap and IndexNow key (app.content, app.spa)."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.spa as spa_module
from app.config import settings
from app.content import pages as pages_module
from app.content import site
from app.content.pages import Page, all_pages, home_faq, parse_page
from app.content.render import render_page
from app.spa import SITE_ORIGIN, mount_spa, render_shell

SHELL = (
    "<html><head><title>x</title>"
    '<meta name="description" content="d" />'
    '<link rel="canonical" href="c" />'
    '<meta property="og:title" content="t" />'
    '<meta property="og:description" content="d" />'
    '<meta property="og:url" content="u" />'
    "<!--faq-jsonld--></head><body><main>spa<!--faq--></main></body></html>"
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(SHELL)
    app = FastAPI()
    mount_spa(app, tmp_path)
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(spa_module, "emit", lambda event_type, **f: emitted.append((event_type, f)))
    return TestClient(app), emitted


def test_every_bundled_page_parses_and_renders() -> None:
    pages = all_pages()
    assert pages, "no content pages found"
    for page in pages.values():
        assert page.title and page.description, page.slug
        doc = render_page(page, "https://example.test")
        assert f'<link rel="canonical" href="https://example.test/{page.slug}" />' in doc
        assert "<h1>" in doc
        for block in re.findall(r'<script type="application/ld\+json">\n(.*?)\n</script>', doc, re.S):
            json.loads(block)


def test_pages_carry_the_preview_image_and_no_doubled_site_name() -> None:
    for page in all_pages().values():
        doc = render_page(page, "https://example.test")
        image = page.og_image or "/og-image.png"
        assert f'<meta property="og:image" content="https://example.test{image}" />' in doc
        assert '<meta name="twitter:card" content="summary_large_image" />' in doc
        title = re.search(r"<title>(.*?)</title>", doc).group(1)
        assert title.count(html.escape(site.SITE_NAME)) == 1, page.slug


def test_own_preview_image_from_front_matter() -> None:
    page = parse_page("x", '+++\ntitle = "T"\ndescription = "D"\nog_image = "/og/x.png"\n+++\nBody\n')
    doc = render_page(page, "https://example.test")
    assert '<meta property="og:image" content="https://example.test/og/x.png" />' in doc
    assert '<meta property="og:image:alt" content="T" />' in doc


def test_every_preview_image_exists_at_1200x630() -> None:
    public = Path(__file__).resolve().parents[2] / "frontend" / "public"
    images = {p.og_image for p in all_pages().values() if p.og_image}
    assert any(i.startswith("/og/fundsxml/") for i in images)
    for image in images:
        head = (public / image.lstrip("/")).read_bytes()[:24]
        assert head[:8] == b"\x89PNG\r\n\x1a\n", image
        assert (int.from_bytes(head[16:20]), int.from_bytes(head[20:24])) == (1200, 630), image


def test_front_matter_is_required() -> None:
    with pytest.raises(ValueError):
        parse_page("x", "# no front matter")


def test_page_fields_and_markdown_escaping() -> None:
    page = parse_page(
        "guides/x",
        '+++\ntitle = "T"\ndescription = "D"\ncta_label = "Go"\ncta_href = "/?sample=a"\n'
        '[[faq]]\nq = "Q?"\na = "A `code`"\n+++\nHello <script>alert(1)</script>\n',
    )
    doc = render_page(page, "https://example.test")
    assert "<script>alert(1)</script>" not in doc
    assert 'href="/?sample=a"' in doc
    assert '"@type": "FAQPage"' in doc
    assert "<code>code</code>" in doc


def test_content_route_served_with_page_view(client) -> None:
    c, emitted = client
    slug = next(iter(all_pages()))
    r = c.get(f"/{slug}?utm_source=hn&utm_campaign=Launch")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Content-Security-Policy" in r.headers
    assert emitted == [
        ("page_view", {"path": f"/{slug}", "status_code": 200, "utm_source": "hn", "utm_campaign": "launch"})
    ]


def test_unknown_content_path_is_404(client) -> None:
    c, emitted = client
    assert c.get("/features/does-not-exist").status_code == 404
    assert c.get("/fundsxml/0.0.0").status_code == 404
    assert emitted == []


def test_home_shell_gets_faq_other_routes_do_not() -> None:
    home = render_shell(SHELL, "")
    assert home_faq()
    assert home.count('<details class="faq">') == len(home_faq())
    assert '"@type": "FAQPage"' in home
    other = render_shell(SHELL, "api-docs")
    assert "<!--faq" not in other
    assert "FAQPage" not in other


def test_sitemap_lists_routes_and_pages(client) -> None:
    c, _ = client
    r = c.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    locs = re.findall(r"<loc>(.*?)</loc>", r.text)
    assert f"{SITE_ORIGIN}/" in locs
    assert f"{SITE_ORIGIN}/fundsxml" in locs
    assert f"{SITE_ORIGIN}/paste" not in locs  # canonical is "/"
    for page in all_pages().values():
        assert (f"{SITE_ORIGIN}/{page.slug}" in locs) is not page.noindex


def test_provider_pages_are_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pages_module, "_providers", [])
    pages_module.all_pages.cache_clear()
    pages_module.register_provider(lambda: [Page(slug="generated/x", title="T", description="D", body="b")])
    try:
        assert pages_module.get_page("generated/x") is not None
    finally:
        monkeypatch.undo()
        pages_module.all_pages.cache_clear()


def test_indexnow_key_file(client, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _ = client
    monkeypatch.setattr(settings, "indexnow_key", "abc123")
    r = c.get("/abc123.txt")
    assert r.status_code == 200 and r.text == "abc123"
    monkeypatch.setattr(settings, "indexnow_key", "")
    assert c.get("/abc123.txt").status_code == 404


def test_embed_route_may_be_framed_and_is_noindex(client) -> None:
    c, emitted = client
    r = c.get("/embed?src=https://example.com/a.xsd")
    assert r.status_code == 200
    assert "frame-ancestors *" in r.headers["Content-Security-Policy"]
    assert "X-Frame-Options" not in r.headers
    assert '<meta name="robots" content="noindex" />' in r.text
    assert emitted[-1] == ("page_view", {"path": "/embed", "status_code": 200, "source": "embed"})
    other = c.get("/")
    assert other.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in other.headers["Content-Security-Policy"]


def test_embed_is_not_in_the_sitemap(client) -> None:
    c, _ = client
    assert "/embed" not in c.get("/sitemap.xml").text


def test_shared_url_link_names_the_schema_in_og_tags() -> None:
    shell = SHELL.replace("<title>x</title>", "<title>x</title>")
    out = render_shell(shell, "url", "https://example.com/schemas/FundsXML%20v4.xsd?raw=1")
    assert 'property="og:title" content="FundsXML v4.xsd — XML Schema in the Online XSD Viewer"' in out
    assert "<title>Load an XSD from a URL" in out
    assert render_shell(shell, "url", "javascript:alert(1)").count("XML Schema in the Online XSD Viewer") == 0


def test_every_page_is_reachable_from_the_guides_hub() -> None:
    """No orphan pages: each indexable page is linked from /guides or from a page /guides links to."""
    import re as _re

    from app.content.pages import HUB_SLUG

    pages = all_pages()

    def links(slug: str) -> set[str]:
        doc = render_page(pages[slug], "https://example.test")
        return {m.split("#")[0].split("?")[0].strip("/") for m in _re.findall(r'href="(/[^"]*)"', doc)}

    first = links(HUB_SLUG)
    reachable = first | {target for slug in first if slug in pages for target in links(slug)}
    orphans = [s for s, p in pages.items() if s != HUB_SLUG and not p.noindex and s not in reachable]
    assert orphans == []


def test_content_pages_link_back_to_the_hub() -> None:
    page = next(p for s, p in all_pages().items() if s != "guides")
    assert 'href="/guides"' in render_page(page, "https://example.test")
