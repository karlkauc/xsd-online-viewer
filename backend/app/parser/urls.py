"""Normalise user-pasted schema URLs and recognise HTML responses (no I/O).

People paste the *browser* address of a file on GitHub or GitLab, which
serves an HTML page around the file rather than the file itself. Rewriting
those to the raw-content URL saves them a confusing "not an XML file" error.
"""

from __future__ import annotations

import re

from httpx import URL

_GITHUB_BLOB_RE = re.compile(r"^/([^/]+)/([^/]+)/(?:blob|raw)/(.+)$")
_GITLAB_BLOB_RE = re.compile(r"^(/.+?)/-/blob/(.+)$")
_BITBUCKET_SRC_RE = re.compile(r"^/([^/]+)/([^/]+)/src/(.+)$")

_HTML_HEAD_RE = re.compile(rb"^\s*(?:<!doctype\s+html|<html)", re.IGNORECASE)


def normalize_schema_url(url: str) -> str:
    """Return the raw-content URL for a GitHub/GitLab/Bitbucket *browse* URL.

    Any other URL is returned unchanged. Query strings are dropped on the
    rewritten forwards because the browse pages take view parameters
    (``?plain=1``) that mean nothing to the raw endpoints.
    """
    try:
        parsed = URL(url)
    except Exception:  # noqa: BLE001 — leave malformed input to the fetcher
        return url
    host = (parsed.host or "").lower()
    path = parsed.path

    if host in ("github.com", "www.github.com"):
        m = _GITHUB_BLOB_RE.match(path)
        if m:
            owner, repo, rest = m.groups()
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"
        return url

    if host in ("gitlab.com", "www.gitlab.com"):
        m = _GITLAB_BLOB_RE.match(path)
        if m:
            project, rest = m.groups()
            return f"https://gitlab.com{project}/-/raw/{rest}"
        return url

    if host in ("bitbucket.org", "www.bitbucket.org"):
        m = _BITBUCKET_SRC_RE.match(path)
        if m:
            workspace, repo, rest = m.groups()
            return f"https://bitbucket.org/{workspace}/{repo}/raw/{rest}"
        return url

    return url


def looks_like_html(content: bytes, content_type: str | None) -> bool:
    """True when a fetched body is a web page rather than an XML file."""
    if content_type and content_type.split(";", 1)[0].strip().lower() == "text/html":
        return True
    head = content.lstrip(b"\xef\xbb\xbf")[:256]
    return bool(_HTML_HEAD_RE.match(head))


def html_response_message(url: str) -> str:
    return (
        f"{url} returned a web page (HTML), not an XML file. Use the direct link to the "
        "file's raw content — on GitHub or GitLab that is the 'Raw' button."
    )
