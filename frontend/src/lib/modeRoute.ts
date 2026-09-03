// Maps the Uploader's input mode to/from the URL path so each input option is
// directly addressable and shareable, e.g. /fundsxml selects the releases tab.
// Mirrors the lightweight URL-manipulation approach in deepLink.ts.
// Keep MODE_TO_PATH, API_DOCS_PATH and API_DOCS_TITLE/DESCRIPTION in sync with ROUTE_META in
// backend/app/spa.py — the server injects per-route <head> metadata into the shell and
// serves the SPA shell only for these paths and answers 404 for anything else.

export type Mode = "file" | "text" | "url" | "releases";

// Static documentation page for the validation API. Not an input mode, but
// it is a client route the server must serve the shell for.
export const API_DOCS_PATH = "/api-docs";

export const API_DOCS_TITLE = "XML validation via API (curl, PowerShell, Python) — Online XSD Viewer";
export const API_DOCS_DESCRIPTION =
  "Validate XML against an XSD from the command line: upload the schema, validate the document, save the JSON error report. Examples for curl, PowerShell and Python, plus size, timeout and rate limits.";

export function isApiDocsRoute(): boolean {
  return window.location.pathname.replace(/\/+$/, "") === API_DOCS_PATH;
}

const MODE_TO_PATH: Record<Mode, string> = {
  file: "/",
  text: "/paste",
  url: "/url",
  releases: "/fundsxml",
};

const PATH_TO_MODE: Record<string, Mode> = {
  "/paste": "text",
  "/url": "url",
  "/fundsxml": "releases",
};

export function readModeFromPath(): Mode {
  // Tolerate a trailing slash, e.g. /fundsxml/.
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  return PATH_TO_MODE[path] ?? "file";
}

export function writeModePath(mode: Mode): void {
  const next = MODE_TO_PATH[mode];
  if (next === window.location.pathname) return;
  // A `?src=`/`?release=` query belongs to the tab it was written for; it
  // would auto-load the wrong thing on another one.
  history.pushState(null, "", `${next}${window.location.hash}`);
}
