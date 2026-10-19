"""Load the content pages: Markdown files with a TOML front matter between ``+++`` lines.

``pages/features/diagram.md`` is served at ``/features/diagram``. Front matter keys:
``title`` (required), ``description`` (required), ``heading`` (h1, defaults to the title),
``lastmod`` (YYYY-MM-DD), ``cta_label``/``cta_href`` (the button into the tool), ``noindex``,
and ``[[faq]]`` tables with ``q``/``a`` (Markdown) that also become FAQPage JSON-LD.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.content import site

CONTENT_DIR = Path(__file__).resolve().parent
PAGES_DIR = CONTENT_DIR / "pages"
FAQ_FILE = CONTENT_DIR / "faq.toml"


@dataclass(frozen=True)
class FaqItem:
    question: str
    answer: str  # Markdown


@dataclass(frozen=True)
class Page:
    slug: str  # path without leading slash, e.g. "features/diagram"
    title: str
    description: str
    body: str  # Markdown
    heading: str = ""
    lastmod: str | None = None
    cta_label: str | None = None
    cta_href: str | None = None
    noindex: bool = False
    faq: tuple[FaqItem, ...] = field(default_factory=tuple)

    @property
    def h1(self) -> str:
        return self.heading or self.title


def _faq(raw: list[dict]) -> tuple[FaqItem, ...]:
    return tuple(FaqItem(question=item["q"].strip(), answer=item["a"].strip()) for item in raw)


def parse_page(slug: str, text: str) -> Page:
    if not text.startswith("+++"):
        raise ValueError(f"content page {slug!r} has no +++ front matter")
    _, front, body = text.split("+++", 2)
    meta = tomllib.loads(front)
    lastmod = meta.get("lastmod")
    return Page(
        slug=slug,
        title=meta["title"],
        description=meta["description"],
        body=body.strip(),
        heading=meta.get("heading", ""),
        lastmod=str(lastmod) if lastmod else None,
        cta_label=meta.get("cta_label"),
        cta_href=meta.get("cta_href"),
        noindex=bool(meta.get("noindex", False)),
        faq=_faq(meta.get("faq", [])),
    )


# Pages built in code from data the app already has (e.g. the bundled sample
# services); each provider returns its pages, registered by the domain module.
PageProvider = Callable[[], list[Page]]
_providers: list[PageProvider] = []


def register_provider(provider: PageProvider) -> None:
    _providers.append(provider)
    all_pages.cache_clear()


HUB_SLUG = "guides"


def _in_section(slug: str, prefixes: tuple[str, ...]) -> bool:
    return any(slug == p.rstrip("/") or (p.endswith("/") and slug.startswith(p)) for p in prefixes)


def _hub(pages: dict[str, Page]) -> Page:
    """/guides: every page listed in ``site.HUB_SECTIONS``, so the SPA needs one link, not a list."""
    lines: list[str] = [site.HUB_INTRO, ""]
    for heading, prefixes in site.HUB_SECTIONS:
        members = [p for slug, p in pages.items() if not p.noindex and _in_section(slug, prefixes)]
        if not members:
            continue
        lines += [f"## {heading}", ""]
        lines += [f"- [{p.h1}](/{p.slug}) — {p.description}" for p in members]
        lines.append("")
    return Page(
        slug=HUB_SLUG,
        title=f"Guides and resources — {site.SITE_NAME}",
        heading="Guides and resources",
        description=site.HUB_INTRO,
        body="\n".join(lines),
        cta_label="Open the viewer",
        cta_href=site.VIEWER_PATH,
    )


@lru_cache(maxsize=1)
def all_pages() -> dict[str, Page]:
    pages: dict[str, Page] = {}
    for path in sorted(PAGES_DIR.rglob("*.md")):
        slug = path.relative_to(PAGES_DIR).with_suffix("").as_posix()
        pages[slug] = parse_page(slug, path.read_text(encoding="utf-8"))
    for provider in _providers:
        for page in provider():
            pages.setdefault(page.slug, page)
    pages.setdefault(HUB_SLUG, _hub(pages))
    return pages


def get_page(slug: str) -> Page | None:
    return all_pages().get(slug)


@lru_cache(maxsize=1)
def home_faq() -> tuple[FaqItem, ...]:
    if not FAQ_FILE.is_file():
        return ()
    return _faq(tomllib.loads(FAQ_FILE.read_text(encoding="utf-8")).get("faq", []))
