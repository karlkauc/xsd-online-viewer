/**
 * Where the loaded schema came from. Kept in the store so the app can
 * (a) build a share link that survives the server's short-lived cache for
 * URL- and release-sourced schemas, and (b) transparently re-submit the
 * schema when a `schema_id` has expired or landed on another instance.
 */
import {
  loadSchemaFromRelease,
  loadSchemaFromUrl,
  uploadSchemaFiles,
  uploadSchemaText,
} from "../api/client";
import type { SchemaResponse } from "../types/schema";

export type SchemaSource =
  | { kind: "upload"; files: File[]; mainFilename?: string }
  | { kind: "text"; content: string; filename?: string }
  | { kind: "url"; url: string }
  | { kind: "release"; tag: string; filename: string };

/** Re-run the load that produced the current schema. */
export function reloadSource(source: SchemaSource): Promise<SchemaResponse> {
  switch (source.kind) {
    case "upload":
      return uploadSchemaFiles(source.files, source.mainFilename);
    case "text":
      return uploadSchemaText(source.content, source.filename);
    case "url":
      return loadSchemaFromUrl(source.url);
    case "release":
      return loadSchemaFromRelease(source.tag, source.filename);
  }
}

/** True when a link can reproduce the load without the recipient having the file. */
export function isShareable(source: SchemaSource | null): boolean {
  return source?.kind === "url" || source?.kind === "release";
}

/** Path + query that re-open this source when visited, or null for local input. */
export function sourcePath(source: SchemaSource | null): string | null {
  if (!source) return null;
  if (source.kind === "url") {
    const params = new URLSearchParams({ src: source.url });
    return `/url?${params.toString()}`;
  }
  if (source.kind === "release") {
    const params = new URLSearchParams({ release: source.tag, file: source.filename });
    return `/fundsxml?${params.toString()}`;
  }
  return null;
}

/** The source encoded in the current address, if any (`/url?src=…`, `/fundsxml?release=…&file=…`). */
export function sourceFromLocation(location: Location = window.location): SchemaSource | null {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const params = new URLSearchParams(location.search);
  if (path === "/url") {
    const src = params.get("src");
    return src && /^https?:\/\//i.test(src) ? { kind: "url", url: src } : null;
  }
  if (path === "/fundsxml") {
    const tag = params.get("release");
    const filename = params.get("file");
    return tag && filename ? { kind: "release", tag, filename } : null;
  }
  return null;
}

/** Absolute link for the current selection; falls back to the plain address for local input. */
export function shareLink(source: SchemaSource | null, location: Location = window.location): string {
  const path = sourcePath(source);
  const base = `${location.origin}${path ?? `${location.pathname}${location.search}`}`;
  return `${base}${location.hash}`;
}

/** Put the shareable path into the address bar (keeping the selection hash). */
export function writeSourcePath(source: SchemaSource | null): void {
  const path = sourcePath(source);
  if (!path) return;
  const next = `${path}${window.location.hash}`;
  if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  history.replaceState(null, "", next);
}
