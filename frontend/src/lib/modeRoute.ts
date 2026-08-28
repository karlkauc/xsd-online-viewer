// Maps the Uploader's input mode to/from the URL path so each input option is
// directly addressable and shareable, e.g. /fundsxml selects the releases tab.
// Mirrors the lightweight URL-manipulation approach in deepLink.ts.
// Keep MODE_TO_PATH and API_DOCS_PATH in sync with SPA_ROUTES in backend/app/spa.py — the server
// serves the SPA shell only for these paths and answers 404 for anything else.

export type Mode = "file" | "text" | "url" | "releases";

// Static documentation page for the validation API. Not an input mode, but
// it is a client route the server must serve the shell for.
export const API_DOCS_PATH = "/api-docs";

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
  history.pushState(null, "", `${next}${window.location.search}${window.location.hash}`);
}
