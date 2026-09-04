import { useCallback, useEffect, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { xml } from "@codemirror/lang-xml";
import { EditorView } from "@codemirror/view";
import { fetchSampleXml, validateXmlText } from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { withSchemaRetry } from "../lib/schemaSession";
import { HANDOFF_UNSUPPORTED_HINT, handoffSupported, openInXmlViewer } from "../lib/xmlViewerHandoff";
import { fetchSchemaBundle } from "../lib/schemaBundle";
import { DesktopAppCard } from "./DesktopAppCard";
import type { ValidationResponse } from "../types/schema";

type Validation =
  | { status: "checking" }
  | { status: "done"; result: ValidationResponse }
  | { status: "failed"; error: string };

export interface SampleTarget {
  elementId: string;
  /** Element name, used for the download file name and the title. */
  name: string;
}

export interface SampleRequest extends SampleTarget {
  /** Other elements the user may switch to (e.g. all document roots). */
  candidates?: SampleTarget[];
}

const EXTENSIONS = [xml(), EditorView.lineWrapping];
const isDark = () => document.documentElement.classList.contains("dark");

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
  const setValidationResult = useSelection((s) => s.setValidationResult);
  const setActiveTab = useSelection((s) => s.setActiveTab);
  const [request, setRequest] = useState<SampleRequest | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [includeOptional, setIncludeOptional] = useState(false);
  const [xml, setXml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [handoff, setHandoff] = useState<"idle" | "sending" | "sent" | "failed" | "unsupported">("idle");

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

  // Check the generated document against the schema right away, so the user
  // sees whether it can be used as-is or which placeholders need attention.
  useEffect(() => {
    if (!request || xml === null) {
      setValidation(null);
      return;
    }
    let cancelled = false;
    setValidation({ status: "checking" });
    const filename = `${request.name}-sample.xml`;
    withSchemaRetry((id) => validateXmlText(id, xml, filename))
      .then((result) => {
        if (!cancelled) setValidation({ status: "done", result });
      })
      .catch((err) => {
        if (!cancelled) setValidation({ status: "failed", error: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [request, xml]);

  const close = useCallback(() => setRequest(null), []);

  const showInValidationTab = useCallback(() => {
    if (validation?.status !== "done") return;
    setValidationResult(validation.result);
    setActiveTab("validation");
    setRequest(null);
  }, [validation, setValidationResult, setActiveTab]);

  const candidates = request?.candidates ?? [];
  const pickCandidate = useCallback(
    (elementId: string) => {
      setRequest((current) => {
        const next = current?.candidates?.find((c) => c.elementId === elementId);
        return current && next ? { ...current, ...next } : current;
      });
      setCopied(false);
      setHandoff("idle");
    },
    [],
  );

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
    if (!handoffSupported()) {
      setHandoff("unsupported");
      return;
    }
    setHandoff("sending");
    const file = new File([xml], `${request.name}-sample.xml`, { type: "application/xml" });
    // The schema goes along so the XML viewer can validate the sample at once.
    void openInXmlViewer(file, { schema: fetchSchemaBundle }).then((ok) => setHandoff(ok ? "sent" : "failed"));
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
          {candidates.length > 1 && (
            <label className="inline-flex items-center gap-2">
              Root element
              <select
                className="px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                value={request.elementId}
                onChange={(e) => pickCandidate(e.target.value)}
              >
                {candidates.map((c) => (
                  <option key={c.elementId} value={c.elementId}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
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

        {validation && (
          <div
            role="status"
            className={
              "px-4 py-2 border-b text-sm flex flex-wrap items-center gap-x-3 gap-y-1 " +
              (validation.status === "done" && validation.result.is_valid
                ? "border-emerald-200 dark:border-emerald-900/60 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-200"
                : validation.status === "done"
                  ? "border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200"
                  : "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-300")
            }
          >
            {validation.status === "checking" && <span>Validating against the schema…</span>}
            {validation.status === "failed" && <span>Could not validate: {validation.error}</span>}
            {validation.status === "done" && validation.result.is_valid && (
              <span className="font-medium">✓ Schema-valid — the document validates against the loaded XSD.</span>
            )}
            {validation.status === "done" && !validation.result.is_valid && (
              <>
                <span className="font-medium">
                  ✗ Not schema-valid: {validation.result.errors.length} validation error
                  {validation.result.errors.length === 1 ? "" : "s"}
                </span>
                <button type="button" className="btn text-xs" onClick={showInValidationTab}>
                  Show in Validation tab
                </button>
                <ul className="basis-full text-xs font-mono space-y-0.5 mt-1">
                  {validation.result.errors.slice(0, 3).map((e, i) => (
                    <li key={i} className="truncate">
                      line {e.line}: {e.message}
                    </li>
                  ))}
                  {validation.result.errors.length > 3 && (
                    <li className="opacity-70">… {validation.result.errors.length - 3} more</li>
                  )}
                </ul>
              </>
            )}
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-auto">
          {error && (
            <p role="alert" className="p-4 text-sm text-red-700 dark:text-red-300">
              Could not generate a sample: {error}
            </p>
          )}
          {!error && xml === null && <p className="p-4 text-sm text-slate-500">Generating…</p>}
          {xml !== null && (
            <div data-testid="sample-xml" className="text-xs">
              <CodeMirror
                value={xml}
                extensions={EXTENSIONS}
                editable={false}
                readOnly
                theme={isDark() ? "dark" : "light"}
                basicSetup={{ lineNumbers: true, foldGutter: true, highlightActiveLine: false }}
              />
            </div>
          )}
          {handoff === "failed" && (
            <p className="px-4 pb-3 text-xs text-slate-500 dark:text-slate-400">
              The XML Viewer did not pick up the sample (popup blocked, or the tab was closed).
              Download it and upload the file in the XML Viewer instead.
            </p>
          )}
          {handoff === "unsupported" && (
            <p className="px-4 pb-3 text-xs text-slate-500 dark:text-slate-400">{HANDOFF_UNSUPPORTED_HINT}</p>
          )}
          {handoff === "sent" && (
            <p className="px-4 pb-3 text-xs text-slate-500 dark:text-slate-400">
              The sample and the schema were sent to the XML Viewer tab.
            </p>
          )}
        </div>
        <div className="px-4 py-2 border-t border-slate-200 dark:border-slate-800">
          <DesktopAppCard variant="inline">
            Need realistic values, several files at once, or reusable generation profiles? Profiled
            XML generation from this schema is built into the free desktop app:
          </DesktopAppCard>
        </div>
      </div>
    </div>
  );
}
