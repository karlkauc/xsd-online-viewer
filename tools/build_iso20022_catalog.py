#!/usr/bin/env python3
"""Write the ISO 20022 message catalogue the "ISO 20022" tab offers.

iso20022.org refuses automated downloads, so the schemas are loaded from a
public mirror on GitHub, pinned to one commit so a message id always means the
same file. This script lists every XSD of that commit, reads each one's root
element and message name, and writes ``backend/app/standards/iso20022_catalog.json``
(committed; the site never calls GitHub to build it, only to load a chosen file):

    backend/.venv/bin/python tools/build_iso20022_catalog.py [--commit <sha>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "app" / "standards" / "iso20022_catalog.json"
REPO = "phoughton/pyiso20022"
DEFAULT_COMMIT = "cfb785fcc5174b09adee1419eb83743c85c79398"
XS = "{http://www.w3.org/2001/XMLSchema}"
_ID_RE = re.compile(r"^([a-z]{4}\.\d{3})\.(\d{3})\.(\d{2})$")


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "online-xsd-viewer"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _label(area: str) -> str:
    return area.replace("_", " ").capitalize()


def _name(type_name: str) -> str:
    """CustomerCreditTransferInitiationV12 -> Customer Credit Transfer Initiation."""
    base = re.sub(r"V\d+$", "", type_name)
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", base)


def _root_and_name(content: bytes) -> tuple[str, str]:
    """The child of the Document type and its type's readable name.

    The business application header (head.001) has no Document: its global
    element (AppHdr) is the root instead.
    """
    doc = etree.fromstring(content)
    types = {ct.get("name"): ct for ct in doc.iter(f"{XS}complexType") if ct.get("name")}
    document = types.get("Document")
    child = document.find(f".//{XS}element") if document is not None else doc.find(f"{XS}element")
    if child is None:
        return "", ""
    return child.get("name", ""), _name(child.get("type", "").split(":")[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    tree = json.loads(_get(f"https://api.github.com/repos/{REPO}/git/trees/{args.commit}?recursive=1"))
    paths = sorted(e["path"] for e in tree["tree"] if e["path"].startswith("xsd/") and e["path"].endswith(".xsd"))
    base = f"https://raw.githubusercontent.com/{REPO}/{args.commit}/"
    messages = []
    for path in paths:
        parts = path.split("/")
        msg_id = parts[-1][: -len(".xsd")]
        m = _ID_RE.match(msg_id)
        if len(parts) != 4 or not m:
            print(f"skipped {path}", file=sys.stderr)
            continue
        root, name = _root_and_name(_get(base + path))
        messages.append(
            {
                "id": msg_id,
                "message": m.group(1),
                "variant": m.group(2),
                "version": m.group(3),
                "area": parts[1],
                "area_label": _label(parts[1]),
                "name": name,
                "root": root,
                "path": path,
            }
        )
        print(f"{msg_id}: {name} ({root})", file=sys.stderr)
    catalog = {
        "source": {
            "repo": REPO,
            "commit": args.commit,
            "license": "MIT (repository); the schemas are published by the ISO 20022 Registration Authority",
            "base_url": base,
            "official": "https://www.iso20022.org/catalogue-messages",
        },
        "messages": messages,
    }
    args.out.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(messages)} messages -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
