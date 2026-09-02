import { useCallback, useEffect, useState } from "react";
import { fetchHealth } from "../api/client";
import { XML_VIEWER_URL } from "../lib/uploadErrors";
import { openFeedback } from "./UploadError";
import { API_DOCS_PATH } from "../lib/modeRoute";
import { KindBadge } from "./TreeView/KindBadge";
import type { SchemaNodeKind } from "../types/schema";

export const GITHUB_REPO_URL = "https://github.com/karlkauc/xsd-online-viewer";

export function openAbout(): void {
  window.dispatchEvent(new CustomEvent("xsdv:open-about"));
}

/**
 * Modal "About" dialog. Opened from anywhere via `openAbout()` — same
 * window-event mechanism as the feedback dialog and the search palette.
 */
const LEGEND_KINDS: SchemaNodeKind[] = [
  "element",
  "attribute",
  "complexType",
  "simpleType",
  "group",
  "attributeGroup",
];

export function AboutDialog() {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener("xsdv:open-about", onOpen);
    return () => window.removeEventListener("xsdv:open-about", onOpen);
  }, []);

  useEffect(() => {
    if (!open || version !== null) return;
    let cancelled = false;
    fetchHealth()
      .then((h) => {
        if (!cancelled) setVersion(h.version);
      })
      .catch(() => {
        if (!cancelled) setVersion("");
      });
    return () => {
      cancelled = true;
    };
  }, [open, version]);

  const close = useCallback(() => setOpen(false), []);

  if (!open) return null;

  const linkClass = "text-blue-600 dark:text-blue-400 hover:underline";

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-start justify-center pt-[10vh] px-4 z-50"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") close();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        className="w-full max-w-lg bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800 p-5"
      >
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h2 id="about-title" className="text-base font-semibold">
              Online XSD Viewer
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {version ? `Version ${version}` : version === "" ? "Version unavailable" : "Loading version…"}
            </p>
          </div>
          <button type="button" className="btn" onClick={close} aria-label="Close about dialog" autoFocus>
            ✕
          </button>
        </div>

        <p className="text-sm">
          Read, understand and share XML Schemas in your browser — tree, XMLSpy-style diagram and
          syntax-highlighted source, all linked to the same selection. No install, no account.
        </p>

        <ul className="mt-3 text-sm space-y-1">
          <li>
            <a className={linkClass} href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
              Source code on GitHub
            </a>
          </li>
          <li>
            <a className={linkClass} href={`${GITHUB_REPO_URL}/issues`} target="_blank" rel="noopener noreferrer">
              Report an issue
            </a>
            {" · "}
            <button
              type="button"
              className={linkClass}
              onClick={() => {
                close();
                openFeedback();
              }}
            >
              Send feedback
            </button>
          </li>
          <li>
            <a className={linkClass} href={API_DOCS_PATH}>
              API documentation
            </a>
            {" — validate XML against an XSD from curl, PowerShell or Python"}
          </li>
          <li>
            <a className={linkClass} href={XML_VIEWER_URL} target="_blank" rel="noopener noreferrer">
              XML Viewer
            </a>
            {" — sister tool for viewing and validating XML documents"}
          </li>
          <li>
            <a className={linkClass} href={`${GITHUB_REPO_URL}/blob/master/LICENSE`} target="_blank" rel="noopener noreferrer">
              MIT License
            </a>
            {" · © 2026 Karl Kauc"}
          </li>
        </ul>

        <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Kind badges
        </p>
        <ul aria-label="Kind badges" className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {LEGEND_KINDS.map((kind) => (
            <li key={kind} className="flex items-center gap-2">
              <KindBadge kind={kind} />
              <span className="font-mono text-xs">{kind}</span>
            </li>
          ))}
        </ul>

        <p className="mt-4 text-[11px] text-slate-500 dark:text-slate-400">
          Uploaded schemas are parsed in memory and dropped after a short cache period. Anonymous
          usage statistics are recorded without your IP address; schema content is never stored.
        </p>
      </div>
    </div>
  );
}
