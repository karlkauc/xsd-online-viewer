import { useCallback, useMemo, useRef, useState } from "react";
import {
  ApiError,
  validateXmlFile,
  validateXmlText,
  validateXmlUrl,
} from "../../api/client";
import { useSelection } from "../../stores/selectionStore";
import { withSchemaRetry } from "../../lib/schemaSession";
import { DesktopAppCard } from "../DesktopAppCard";
import type { ValidationErrorItem } from "../../types/schema";

type Mode = "file" | "text" | "url";

const MODE_LABELS: Record<Mode, string> = {
  file: "File",
  text: "Paste",
  url: "URL",
};

const SEVERITY_TONE: Record<ValidationErrorItem["severity"], string> = {
  fatal: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  error: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  warning:
    "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

/** Slice the ±1 line window around a 1-based line number. */
function contextWindow(
  reformatted: string | null,
  line: number | null,
): { number: number; text: string; isTarget: boolean }[] {
  if (reformatted === null || line === null || line < 1) return [];
  const lines = reformatted.split("\n");
  const start = Math.max(1, line - 1);
  const end = Math.min(lines.length, line + 1);
  const out: { number: number; text: string; isTarget: boolean }[] = [];
  for (let n = start; n <= end; n += 1) {
    out.push({ number: n, text: lines[n - 1] ?? "", isTarget: n === line });
  }
  return out;
}

function ErrorCard({ error }: { error: ValidationErrorItem }) {
  const setSelected = useSelection((s) => s.setSelected);
  const setActiveTab = useSelection((s) => s.setActiveTab);
  const reformatted = useSelection((s) => s.validationResult?.reformatted_xml ?? null);
  const lines = useMemo(
    () => contextWindow(reformatted, error.line),
    [reformatted, error.line],
  );

  const jumpToXsd = useCallback(() => {
    if (!error.xsd_ref) return;
    setSelected(error.xsd_ref.id);
    setActiveTab("text");
  }, [error.xsd_ref, setSelected, setActiveTab]);

  return (
    <li className="panel rounded-md p-3">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <span
          className={
            "px-1.5 py-0.5 rounded text-xs font-semibold uppercase " +
            SEVERITY_TONE[error.severity]
          }
        >
          {error.severity}
        </span>
        {error.line !== null && (
          <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
            line {error.line}
            {error.column ? `:${error.column}` : ""}
          </span>
        )}
        {error.type_name && (
          <span className="font-mono text-[11px] text-slate-400 dark:text-slate-500">
            {error.type_name}
          </span>
        )}
      </div>
      <p className="text-sm text-slate-800 dark:text-slate-200">{error.message}</p>

      {lines.length > 0 && (
        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 dark:bg-slate-900/40 text-xs font-mono">
          {lines.map((l) => (
            <div
              key={l.number}
              className={
                "px-2 py-0.5 flex gap-3 " +
                (l.isTarget
                  ? "bg-blue-100/70 dark:bg-blue-900/30 shadow-[inset_3px_0_0_0_#3b82f6] dark:shadow-[inset_3px_0_0_0_#60a5fa]"
                  : "")
              }
            >
              <span className="select-none text-slate-400 dark:text-slate-600 tabular-nums w-10 text-right shrink-0">
                {l.number}
              </span>
              <span className="whitespace-pre">{l.text}</span>
            </div>
          ))}
        </pre>
      )}

      {error.xsd_ref && (
        <button
          type="button"
          className="btn mt-2 text-xs"
          onClick={jumpToXsd}
          title={`Show ${error.xsd_ref.qname} in the schema source`}
        >
          View in XSD ({error.xsd_ref.qname})
        </button>
      )}
    </li>
  );
}

export function ValidationPanel() {
  const schemaId = useSelection((s) => s.schemaId);
  const result = useSelection((s) => s.validationResult);
  const setResult = useSelection((s) => s.setValidationResult);

  const [mode, setMode] = useState<Mode>("file");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);

  const run = useCallback(
    async (fn: () => Promise<void>) => {
      setError(null);
      setBusy(true);
      try {
        await fn();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const onFile = useCallback(
    (file: File) => {
      if (!schemaId) return;
      void run(async () => {
        setResult(await withSchemaRetry((id) => validateXmlFile(id, file)));
      });
    },
    [schemaId, run, setResult],
  );

  const onText = useCallback(() => {
    if (!schemaId) return;
    void run(async () => {
      setResult(await withSchemaRetry((id) => validateXmlText(id, text)));
    });
  }, [schemaId, text, run, setResult]);

  const onUrl = useCallback(() => {
    if (!schemaId) return;
    void run(async () => {
      setResult(await withSchemaRetry((id) => validateXmlUrl(id, url.trim())));
    });
  }, [schemaId, url, run, setResult]);

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-3xl mx-auto">
        <h2 className="text-xl font-semibold mb-2">
          Validate an XML document
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-5">
          Check an XML file against the currently loaded schema. The document is
          reformatted first, so reported line numbers match the formatted text
          shown below.
        </p>

        <div className="flex flex-wrap gap-1 mb-4" role="tablist">
          {(["file", "text", "url"] as Mode[]).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              className={
                "px-3 py-1.5 text-sm font-medium rounded-md " +
                (mode === value
                  ? "bg-accent text-white dark:bg-accent-dark dark:text-slate-950"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700")
              }
              onClick={() => setMode(value)}
            >
              {MODE_LABELS[value]}
            </button>
          ))}
        </div>

        {mode === "file" && (
          <div className="panel rounded-lg p-8 text-center">
            <input
              ref={fileInput}
              type="file"
              accept=".xml,application/xml,text/xml"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onFile(file);
              }}
            />
            <p className="mb-4 text-slate-700 dark:text-slate-300">
              Choose an XML file to validate.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => fileInput.current?.click()}
              disabled={busy}
            >
              Choose file…
            </button>
          </div>
        )}

        {mode === "text" && (
          <div className="panel rounded-lg p-4">
            <textarea
              className="w-full h-56 font-mono text-sm p-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              placeholder="<root>…</root>"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button
              type="button"
              className="btn btn-primary mt-3"
              disabled={busy || !text.trim()}
              onClick={onText}
            >
              Validate
            </button>
          </div>
        )}

        {mode === "url" && (
          <div className="panel rounded-lg p-4">
            <input
              type="url"
              placeholder="https://example.com/document.xml"
              className="w-full font-mono text-sm px-3 py-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <button
              type="button"
              className="btn btn-primary mt-3"
              disabled={busy || !url.trim()}
              onClick={onUrl}
            >
              Validate
            </button>
          </div>
        )}

        {busy && <p className="mt-4 text-sm text-slate-500">Validating…</p>}
        {error && (
          <p
            className="mt-4 text-sm text-red-600 dark:text-red-400"
            role="alert"
          >
            {error}
          </p>
        )}

        {result && !busy && (
          <div className="mt-6">
            {result.is_valid ? (
              <div
                className="rounded-md px-4 py-3 text-sm font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                role="status"
              >
                ✓ Schema-valid — the document conforms to the loaded schema.
              </div>
            ) : (
              <div
                className="rounded-md px-4 py-3 text-sm font-semibold bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
                role="status"
              >
                ✗ {result.errors.length}{" "}
                {result.errors.length === 1 ? "error" : "errors"} — the
                document is not schema-valid.
              </div>
            )}

            {result.reformatted_xml === null && (
              <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
                The document is not well-formed XML, so it could not be
                reformatted. The line/column below refers to the original
                input.
              </p>
            )}

            {result.errors.length > 0 && (
              <ul className="mt-4 space-y-3">
                {result.errors.map((err, i) => (
                  <ErrorCard key={i} error={err} />
                ))}
              </ul>
            )}
          </div>
        )}
        {result && !busy && (
          <DesktopAppCard variant="inline" className="mt-6">
            Validate whole folders, add Schematron business rules, or fix the document in a schema-aware
            editor with the free desktop app:
          </DesktopAppCard>
        )}
      </div>
    </div>
  );
}
