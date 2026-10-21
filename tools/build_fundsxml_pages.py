#!/usr/bin/env python3
"""Write one content page per FundsXML release, with the changes to the previous release.

The pages (``backend/app/content/pages/fundsxml/<tag>.md`` and the overview
``fundsxml/releases.md``) are committed, so the site never calls GitHub to
render them. Run again after a new release and deploy:

    backend/.venv/bin/python tools/build_fundsxml_pages.py

Every schema is parsed with the viewer's own parser (``parse_files_map``, the
path the "FundsXML Releases" tab uses) and compared with ``schema_diff``. Each
release page also gets its link-preview image, ``frontend/public/og/fundsxml/<tag>.png``
(``fundsxml_og_image.py``; needs Pillow from the backend's dev extra).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.schema_diff import SchemaDiff, diff
from app.parser.xsd_parser import parse_files_map, pick_main_xsd

sys.path.insert(0, str(ROOT / "tools"))
import fundsxml_og_image  # noqa: E402

RELEASES_URL = "https://api.github.com/repos/fundsxml/schema/releases?per_page=100"
OUT = ROOT / "backend" / "app" / "content" / "pages" / "fundsxml"
OG_OUT = ROOT / "frontend" / "public" / "og" / "fundsxml"
# Long lists help nobody on a web page; the viewer has the complete schema.
MAX_CONTAINERS = 80
MAX_ITEMS = 40


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "online-xsd-viewer", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", tag))


def _code(name: str) -> str:
    return f"`{name.replace('`', '')}`"


def _cap(items: list[str], limit: int = MAX_ITEMS) -> list[str]:
    return items if len(items) <= limit else [*items[:limit], f"… and {len(items) - limit} more"]


def _notes(body: str | None) -> str:
    """Release notes from GitHub, headings demoted below the page's own."""
    text = (body or "").strip().replace("\r\n", "\n")
    return re.sub(r"^(#{1,4}) ", lambda m: "#" * min(len(m.group(1)) + 2, 6) + " ", text, flags=re.M)


def _diff_markdown(d: SchemaDiff, prev: str) -> list[str]:
    if d.empty:
        return [f"No structural changes to elements, types or enumerations since {prev}."]
    out: list[str] = []
    for label, items in (
        ("New global elements", d.added_elements),
        ("Removed global elements", d.removed_elements),
        ("New types", d.added_types),
        ("Removed types", d.removed_types),
    ):
        if items:
            out += ["", f"**{label}:** " + ", ".join(_code(i) for i in _cap(items))]
    if d.containers:
        out += ["", "### Changed content models", ""]
        for change in d.containers[:MAX_CONTAINERS]:
            out.append(f"- {_code(change.container)}")
            out += [f"  - added {_code(i)}" for i in _cap(change.added, 15)]
            out += [f"  - removed {_code(i)}" for i in _cap(change.removed, 15)]
            out += [f"  - changed {_code(i)}" for i in _cap(change.changed, 15)]
        if len(d.containers) > MAX_CONTAINERS:
            out.append(f"- … and {len(d.containers) - MAX_CONTAINERS} more types")
    if d.enums:
        out += ["", "### Changed code lists (enumerations)", ""]
        for e in d.enums[:MAX_CONTAINERS]:
            parts = []
            if e.added:
                parts.append("added " + ", ".join(_code(v) for v in _cap(e.added, 20)))
            if e.removed:
                parts.append("removed " + ", ".join(_code(v) for v in _cap(e.removed, 20)))
            out.append(f"- {_code(e.type_name)}: " + "; ".join(parts))
    return out


def _front(
    title: str, description: str, cta_label: str, cta_href: str, lastmod: str, og_image: str | None = None
) -> list[str]:
    return [
        "+++",
        f"title = {json.dumps(title)}",
        f"description = {json.dumps(description)}",
        f"lastmod = {lastmod}",
        f"cta_label = {json.dumps(cta_label)}",
        f"cta_href = {json.dumps(cta_href)}",
        *([f"og_image = {json.dumps(og_image)}"] if og_image else []),
        "+++",
        "",
    ]


def _og_image(tag: str, published: str, main_file: str, model, d: SchemaDiff | None, prev: str | None) -> str:
    """Draw the release's preview image; returns its path on the site."""
    stats = [
        fundsxml_og_image.Stat(str(sum(1 for t in model.complex_types if t.name)), "complex types"),
        fundsxml_og_image.Stat(str(sum(1 for t in model.simple_types if t.name)), "simple types"),
    ]
    subtitle = f"Released {published} · {main_file}"
    if d is not None:
        subtitle += f" · compared with {prev}"
        stats += [
            fundsxml_og_image.Stat(f"+{len(d.added_types)}", "new types"),
            fundsxml_og_image.Stat(str(len(d.containers) + len(d.enums)), "changed types"),
        ]
    fundsxml_og_image.render(OG_OUT / f"{tag}.png", tag, subtitle, stats, f"xsd-viewer.online/fundsxml/{tag}")
    return f"/og/fundsxml/{tag}.png"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    releases = [r for r in json.loads(_get(RELEASES_URL)) if not r.get("draft")]
    releases = [r for r in releases if any(a["name"].lower().endswith(".xsd") for a in r.get("assets", []))]
    releases.sort(key=lambda r: _version_key(r["tag_name"]))
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str, int]] = []
    previous = None
    for release in releases:
        tag = release["tag_name"]
        files = {a["name"]: _get(a["browser_download_url"]) for a in release["assets"] if a["name"].lower().endswith(".xsd")}
        main_file = pick_main_xsd(files) or next(iter(files))
        model = parse_files_map(files, main_file)
        published = release["published_at"][:10]
        # Global elements of the main file; xmldsig's own globals are not FundsXML roots.
        main_ids = {f.id for f in model.files if f.relationship == "main"} if model.files else set()
        roots = [
            e.name
            for e in model.elements
            if e.name and (not main_ids or (e.source_ref is not None and e.source_ref.file_id in main_ids))
        ]
        d = diff(previous[1], model) if previous else None
        lines = _front(
            f"FundsXML {tag} schema: structure and changes" + (f" since {previous[0]}" if previous else ""),
            f"FundsXML {tag} XML Schema ({main_file}), released {published}: global elements, types and "
            + (f"what changed compared with FundsXML {previous[0]}." if previous else "structure."),
            f"Open FundsXML {tag} in the viewer",
            f"/fundsxml?release={tag}&file={main_file}",
            date.today().isoformat(),
            _og_image(tag, published, main_file, model, d, previous[0] if previous else None),
        )
        lines += [
            f"FundsXML {tag} was published on {published} in the "
            f"[fundsxml/schema]({release['html_url']}) repository.",
            "",
            f"- **Main schema:** {_code(main_file)}" + (f" (+ {', '.join(_code(n) for n in files if n != main_file)})" if len(files) > 1 else ""),
            f"- **Target namespace:** {_code(model.target_namespace) if model.target_namespace else 'none'}",
            f"- **Root element{'s' if len(roots) != 1 else ''}:** {', '.join(_code(r) for r in _cap(roots, 10))}",
            f"- **Complex types:** {sum(1 for t in model.complex_types if t.name)}, "
            f"**simple types:** {sum(1 for t in model.simple_types if t.name)}, "
            f"**global elements:** {len(roots)}",
            "",
        ]
        change_count = 0
        if previous and d is not None:
            change_count = len(d.containers) + len(d.enums) + len(d.added_types) + len(d.removed_types)
            lines += [f"## Changes since FundsXML {previous[0]}", *_diff_markdown(d, previous[0]), ""]
        notes = _notes(release.get("body"))
        if notes:
            lines += ["## Release notes", "", notes, ""]
        lines += ["See [all FundsXML releases](/fundsxml/releases)."]
        (args.out / f"{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        rows.append((tag, published, main_file, change_count))
        previous = (tag, model)
        print(f"{tag}: {change_count} changes", file=sys.stderr)

    overview = _front(
        "FundsXML schema releases: every version with its changes",
        "All FundsXML XML Schema releases from the official fundsxml/schema repository, with the changes "
        "between versions and a link to browse each schema online.",
        "Browse the latest FundsXML schema",
        "/fundsxml",
        date.today().isoformat(),
    )
    overview += [
        "FundsXML is the XML standard for exchanging fund data — static data, holdings, prices, "
        "regulatory reporting — between asset managers, custodians, distributors and data vendors. "
        "Each release below has a page with its structure and what changed compared with the previous one.",
        "",
        "| Release | Published | Main schema | Changed types and code lists |",
        "|---|---|---|---|",
    ]
    for tag, published, main_file, change_count in reversed(rows):
        overview.append(f"| [FundsXML {tag}](/fundsxml/{tag}) | {published} | {_code(main_file)} | {change_count} |")
    (args.out / "releases.md").write_text("\n".join(overview) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
