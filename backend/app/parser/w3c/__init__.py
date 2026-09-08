"""Bundled W3C schemas that real-world schemas import without shipping.

``xml.xsd`` (xml:lang, xml:space), XML Signature, XML Encryption and XLink
are imported by e-invoicing, tax, GML and SAF-T schemas by namespace alone
or by an absolute w3.org URL. Users upload the main file without them, so
the import stays unresolved and validation fails with "does not resolve".
Serving the four files from the package makes those imports work offline
and keeps w3.org (which throttles automated clients) out of the request
path. Files are unmodified W3C originals; see LICENSE-W3C.txt.
"""

from __future__ import annotations

import posixpath
from functools import cache
from importlib import resources
from urllib.parse import urlsplit

BUNDLED: dict[str, str] = {
    "http://www.w3.org/XML/1998/namespace": "xml.xsd",
    "http://www.w3.org/2000/09/xmldsig#": "xmldsig-core-schema.xsd",
    "http://www.w3.org/2001/04/xmlenc#": "xenc-schema.xsd",
    "http://www.w3.org/1999/xlink": "xlink.xsd",
}

_FILENAMES = frozenset(BUNDLED.values())


@cache
def _read(filename: str) -> bytes:
    return resources.files(__package__).joinpath(filename).read_bytes()


def bytes_for_namespace(namespace: str | None) -> tuple[str, bytes] | None:
    """``(filename, content)`` of the bundled schema for ``namespace``, if any."""
    filename = BUNDLED.get(namespace or "")
    if filename is None:
        return None
    return filename, _read(filename)


def bytes_for_location(location: str) -> tuple[str, bytes] | None:
    """``(filename, content)`` when ``location`` (path or URL) names a bundled file."""
    path = urlsplit(location).path if "://" in location else location.split("?", 1)[0]
    filename = posixpath.basename(path.replace("\\", "/"))
    if filename not in _FILENAMES:
        return None
    return filename, _read(filename)
