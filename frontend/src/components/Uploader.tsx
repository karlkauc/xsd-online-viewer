import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  loadSchemaFromRelease,
  loadSchemaFromUrl,
  uploadSchemaFile,
  uploadSchemaText,
} from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { readModeFromPath, writeModePath, type Mode } from "../lib/modeRoute";
import { FundsXmlReleases } from "./FundsXmlReleases";
import { UploadError } from "./UploadError";
import { looksLikeSchema, shouldSniff, XML_VIEWER_URL } from "../lib/uploadErrors";

const MODE_LABELS: Record<Mode, string> = {
  file: "File / ZIP",
  text: "Paste",
  url: "URL",
  releases: "FundsXML Releases",
};

export function Uploader() {
  const setSchema = useSelection((s) => s.setSchema);
  const [mode, setMode] = useState<Mode>(() => readModeFromPath());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorFile, setErrorFile] = useState<string | undefined>(undefined);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  // The file of the last attempt, kept so an XML document can be handed to
  // the XML viewer without asking the user to pick it again.
  const [lastFile, setLastFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [mainFilename, setMainFilename] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    async (file: File, { force = false }: { force?: boolean } = {}) => {
      setError(null);
      setErrorFile(file.name);
      setPendingFile(null);
      setLastFile(file);
      setBusy(true);
      try {
        if (!force && shouldSniff(file.name)) {
          // Avoid shipping a multi-MB XML document only to get a 400 back.
          const head = await file.slice(0, 2048).text();
          if (!looksLikeSchema(head)) {
            setPendingFile(file);
            setError(`${file.name}: no <xs:schema> root found — this looks like an XML document, not an XML Schema`);
            return;
          }
        }
        const response = await uploadSchemaFile(file, mainFilename.trim() || undefined);
        setSchema(response.schema_id, response.model);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [mainFilename, setSchema],
  );

  const handleText = useCallback(async () => {
    setError(null);
    setErrorFile(undefined);
    setPendingFile(null);
    setLastFile(null);
    setBusy(true);
    try {
      const response = await uploadSchemaText(text);
      setSchema(response.schema_id, response.model);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [text, setSchema]);

  const loadFromUrl = useCallback(
    async (target: string) => {
      setError(null);
      setErrorFile(target);
      setPendingFile(null);
      setLastFile(null);
      setBusy(true);
      try {
        const response = await loadSchemaFromUrl(target);
        setSchema(response.schema_id, response.model);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [setSchema],
  );

  const handleUrl = useCallback(() => {
    void loadFromUrl(url.trim());
  }, [url, loadFromUrl]);

  const loadFromRelease = useCallback(
    async (tagName: string, filename: string) => {
      setError(null);
      setErrorFile(`${tagName}/${filename}`);
      setPendingFile(null);
      setLastFile(null);
      setBusy(true);
      try {
        const response = await loadSchemaFromRelease(tagName, filename);
        setSchema(response.schema_id, response.model);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [setSchema],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragOver(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  // Reflect the selected tab in the URL path so each option is shareable.
  useEffect(() => {
    writeModePath(mode);
  }, [mode]);

  // Follow browser back/forward between the input options.
  useEffect(() => {
    const onPopState = () => setMode(readModeFromPath());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  return (
    <div className="max-w-3xl mx-auto p-6 md:p-10">
      <h2 className="text-xl font-semibold mb-2">Load an XSD schema</h2>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Drop an <code>.xsd</code> file or a <code>.zip</code> archive (for multi-file schemas),
        paste schema source, or point to a URL.
      </p>
      <p className="text-xs text-slate-500 dark:text-slate-400 -mt-4 mb-6">
        Have an XML <strong>document</strong> to inspect or validate instead? Use our sister tool{" "}
        <a href={XML_VIEWER_URL} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
          XML Viewer
        </a>
        .
      </p>

      <div className="flex flex-wrap gap-1 mb-4" role="tablist">
        {(["file", "text", "url", "releases"] as Mode[]).map((value) => (
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
        <div
          className={
            "panel rounded-lg p-8 text-center transition-colors " +
            (dragOver ? "border-accent bg-blue-50/60 dark:bg-blue-950/20" : "")
          }
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <input
            ref={fileInput}
            type="file"
            accept=".xsd,.xml,.zip,application/zip,application/xml,text/xml"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          <p className="mb-4 text-slate-700 dark:text-slate-300">
            Drop a file here, or click the button to choose one.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
          >
            Choose file…
          </button>
          <label className="block mt-4 text-xs text-slate-500 dark:text-slate-400">
            For ZIP uploads, optionally specify which file is the main schema:
            <input
              type="text"
              placeholder="main.xsd"
              className="ml-2 px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              value={mainFilename}
              onChange={(e) => setMainFilename(e.target.value)}
            />
          </label>
        </div>
      )}

      {mode === "text" && (
        <div className="panel rounded-lg p-4">
          <textarea
            className="w-full h-64 font-mono text-sm p-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
            placeholder="<xs:schema …>"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-primary mt-3"
            disabled={busy || !text.trim()}
            onClick={() => void handleText()}
          >
            Parse
          </button>
        </div>
      )}

      {mode === "url" && (
        <div className="panel rounded-lg p-4">
          <input
            type="url"
            placeholder="https://schemas.example.com/thing.xsd"
            className="w-full font-mono text-sm px-3 py-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
            Any public <code>http(s)</code> URL works. Private/loopback
            addresses are blocked, and admins can lock the endpoint down to
            specific hosts via <code>ALLOWED_SCHEMA_HOSTS</code>.
          </p>
          <button
            type="button"
            className="btn btn-primary mt-3"
            disabled={busy || !url.trim()}
            onClick={handleUrl}
          >
            Load
          </button>
        </div>
      )}

      {mode === "releases" && (
        <FundsXmlReleases
          onSelect={(tagName, filename) =>
            void loadFromRelease(tagName, filename)
          }
          busy={busy}
        />
      )}

      {busy && <p className="mt-4 text-sm text-slate-500">Parsing…</p>}
      {error && (
        <UploadError
          message={error}
          schemaName={errorFile}
          file={lastFile ?? undefined}
          onUploadAnyway={pendingFile ? () => void handleFile(pendingFile, { force: true }) : undefined}
        />
      )}
    </div>
  );
}
