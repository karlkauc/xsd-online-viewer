import { useCallback, useRef, useState } from "react";
import {
  ApiError,
  loadSchemaFromRelease,
  loadSchemaFromUrl,
  uploadSchemaFile,
  uploadSchemaText,
} from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { FundsXmlReleases } from "./FundsXmlReleases";

type Mode = "file" | "text" | "url" | "releases";

const MODE_LABELS: Record<Mode, string> = {
  file: "File / ZIP",
  text: "Paste",
  url: "URL",
  releases: "FundsXML Releases",
};

export function Uploader() {
  const setSchema = useSelection((s) => s.setSchema);
  const [mode, setMode] = useState<Mode>("file");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [mainFilename, setMainFilename] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setBusy(true);
      try {
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

  return (
    <div className="max-w-3xl mx-auto p-6 md:p-10">
      <h2 className="text-xl font-semibold mb-2">Load an XSD schema</h2>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Drop an <code>.xsd</code> file or a <code>.zip</code> archive (for multi-file schemas),
        paste schema source, or point to a URL.
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
            URL fetching must be allowed server-side via <code>ALLOWED_SCHEMA_HOSTS</code>.
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
        <p className="mt-4 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
