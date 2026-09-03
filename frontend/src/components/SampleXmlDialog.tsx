import { useCallback, useEffect, useState } from "react";
import { fetchSampleXml } from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { withSchemaRetry } from "../lib/schemaSession";
import { openInXmlViewer } from "../lib/xmlViewerHandoff";

export interface SampleRequest {
  elementId: string;
  /** Element name, used for the download file name and the title. */
  name: string;
}

export function openSampleXml(request: SampleRequest): void {
  window.dispatchEvent(new CustomEvent<SampleRequest>("xsdv:open-sample", { detail: request }));
}

/**
 * Modal showing a generated sample instance for one element. Opened from
 * anywhere via `openSampleXml()` — same window-event mechanism as the About
 * and Feedback dialogs. Fetches on open and again when the options change.
 */
export function SampleXmlDialog() {
  const schemaId = useSelection((s) => s.schemaId);
  const [request, setRequest] = useState<SampleRequest | null>(null);
  const [includeOptional, setIncludeOptional] = useState(false);
  const [xml, setXml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [handoff, setHandoff] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  useEffect(() => {
    const onOpen = (event: Event) => {
      setRequest((event as CustomEvent<SampleRequest>).detail);
      setCopied(false);
      setHandoff("idle");
    };
    window.addEventListener("xsdv:open-sample", onOpen);
    return () => window.removeEventListener("xsdv:open-sample", onOpen);
  }, []);

  useEffect(() => {
    if (!request || !schemaId) return;
    let cancelled = false;
    setXml(null);
    setError(null);
    withSchemaRetry((id) => fetchSampleXml(id, request.elementId, { includeOptional }))
      .then((text) => {
        if (!cancelled) setXml(text);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [request, schemaId, includeOptional]);

  const close = useCallback(() => setRequest(null), []);

  useEffect(() => {
    if (!request) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [request, close]);

  const copy = useCallback(async () => {
    if (!xml) return;
    try {
      await navigator.clipboard.writeText(xml);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [xml]);

  const download = useCallback(() => {
    if (!xml || !request) return;
    const blob = new Blob([xml], { type: "application/xml" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${request.name}-sample.xml`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }, [xml, request]);

  const sendToXmlViewer = useCallback(() => {
    if (!xml || !request) return;
    setHandoff("sending");
    const file = new File([xml], `${request.name}-sample.xml`, { type: "application/xml" });
    void openInXmlViewer(file).then((ok) => setHandoff(ok ? "sent" : "failed"));
  }, [xml, request]);

  if (!request) return null;

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-start justify-center pt-[6vh] px-4 z-50"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sample-title"
        className="w-full max-w-3xl max-h-[88vh] flex flex-col bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800"
      >
        <div className="flex items-start justify-between gap-3 p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="min-w-0">
            <h2 id="sample-title" className="text-base font-semibold truncate">
              Sample XML for &lt;{request.name}&gt;
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Required content only, first choice branch, first enumeration value. Placeholder
              values need replacing; comments mark what could not be resolved.
            </p>
          </div>
          <button
            type="button"
            className="btn text-xs shrink-0"
            onClick={close}
            aria-label="Close sample dialog"
          >
            Close
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 px-4 py-2 border-b border-slate-200 dark:border-slate-800 text-sm">
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeOptional}
              onChange={(e) => setIncludeOptional(e.target.checked)}
            />
            Include optional elements and attributes
          </label>
          <div className="ml-auto flex flex-wrap gap-2">
            <button type="button" className="btn text-xs" disabled={!xml} onClick={() => void copy()}>
              {copied ? "Copied ✓" : "Copy"}
            </button>
            <button type="button" className="btn text-xs" disabled={!xml} onClick={download}>
              Download
            </button>
            <button
              type="button"
              className="btn text-xs"
              disabled={!xml || handoff === "sending"}
              onClick={sendToXmlViewer}
            >
              Open in XML Viewer ↗
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto p-4">
          {error && (
            <p role="alert" className="text-sm text-red-700 dark:text-red-300">
              Could not generate a sample: {error}
            </p>
          )}
          {!error && xml === null && <p className="text-sm text-slate-500">Generating…</p>}
          {xml !== null && (
            <pre className="font-mono text-xs leading-relaxed whitespace-pre text-slate-800 dark:text-slate-100">
              {xml}
            </pre>
          )}
          {handoff === "failed" && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Could not send the sample automatically (popup blocked?). Download it and upload the
              file in the XML Viewer instead.
            </p>
          )}
          {handoff === "sent" && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              The sample was sent to the XML Viewer tab.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
