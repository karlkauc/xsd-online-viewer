"""Per-site constants for the content pages; the rest of ``app.content`` is shared with the siblings."""

from __future__ import annotations

SITE_NAME = "Online XSD Viewer"
# Where the "Open the viewer" button in the page header points.
VIEWER_PATH = "/"
LOGO_PATH = "/favicon.svg"
# This site's key in FAMILY; its own entry is shown without a link.
SELF = "xsd"

# Same list, same order on all three viewers. Sister links go through /go/
# so clicks are counted without client-side tracking.
FAMILY: tuple[tuple[str, str, str], ...] = (
    ("xsd", "XSD Viewer", "/go/xsd-viewer"),
    ("xml", "XML Viewer", "/go/xml-viewer"),
    ("odata", "OData Viewer", "/go/odata-viewer"),
    ("desktop", "Desktop app", "/go/freexmltoolkit"),
)
