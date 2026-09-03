import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  loadSchemaFromRelease,
  loadSchemaFromUrl,
  uploadSchemaFiles,
  uploadSchemaText,
} from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { readModeFromPath, writeModePath, type Mode } from "../lib/modeRoute";
import { FundsXmlReleases } from "./FundsXmlReleases";
import { UploadError } from "./UploadError";
import { looksLikeSchema, shouldSniff, XML_VIEWER_URL } from "../lib/uploadErrors";
import { listZipEntries, pickMainXsd, xsdEntries } from "../lib/zipEntries";
import { sourceFromLocation, writeSourcePath, type SchemaSource } from "../lib/schemaSource";
import { COARSE_POINTER_QUERY, useMediaQuery } from "../lib/useMediaQuery";

/** Files chosen but not yet uploaded because the main schema needs confirming. */
interface Staged {
  files: File[];
  /** `.xsd` entry paths (ZIP) or file names (loose files) to choose from. */
  candidates: string[];
  main: string;
  kind: "zip" | "files";
}

function isZip(file: File): boolean {
  return file.name.toLowerCase().endsWith(".zip") || file.type.endsWith("zip");
}

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
  const [staged, setStaged] = useState<Staged | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  // Finger input has no drag-and-drop; say so instead of inviting a drop.
  const coarsePointer = useMediaQuery(COARSE_POINTER_QUERY);

  const upload = useCallback(
    async (files: File[], mainFilename?: string, { force = false }: { force?: boolean } = {}) => {
      const file = files[0];
      setError(null);
      setErrorFile(mainFilename ?? file.name);
      setPendingFile(null);
      setLastFile(files.length === 1 ? file : null);
      setBusy(true);
      try {
        if (!force && files.length === 1 && shouldSniff(file.name)) {
          // Avoid shipping a multi-MB XML document only to get a 400 back.
          const head = await file.slice(0, 2048).text();
          if (!looksLikeSchema(head)) {
            setPendingFile(file);
            setError(`${file.name}: no <xs:schema> root found — this looks like an XML document, not an XML Schema`);
            return;
          }
        }
        const response = await uploadSchemaFiles(files, mainFilename);
        setStaged(null);
        setSchema(response.schema_id, response.model, { kind: "upload", files, mainFilename });
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [setSchema],
  );

  /**
   * Decide what to do with the chosen files: a single schema uploads right
   * away; a ZIP with several `.xsd` entries or a set of loose files first
   * shows a picker for the main schema, pre-selected by the same heuristic
   * the backend uses.
   */
  const stageFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      setError(null);
      setPendingFile(null);
      setStaged(null);
      if (files.length === 1) {
        const file = files[0];
        if (!isZip(file)) return upload(files);
        const entries = await listZipEntries(file).catch(() => [] as string[]);
        const candidates = xsdEntries(entries);
        if (candidates.length <= 1) return upload(files);
        setStaged({ files, candidates, main: pickMainXsd(entries) ?? candidates[0], kind: "zip" });
        return;
      }
      const names = files.map((f) => f.name);
      const candidates = xsdEntries(names);
      if (candidates.length === 0) {
        setErrorFile(names[0]);
        setError(`none of the ${files.length} files is an .xsd schema (${names.slice(0, 5).join(", ")})`);
        return;
      }
      const contents = new Map<string, string>();
      await Promise.all(
        files
          .filter((f) => candidates.includes(f.name))
          .map(async (f) => contents.set(f.name, await f.slice(0, 512_000).text())),
      );
      setStaged({ files, candidates, main: pickMainXsd(names, contents) ?? candidates[0], kind: "files" });
    },
    [upload],
  );

  const handleText = useCallback(async () => {
    setError(null);
    setErrorFile(undefined);
    setPendingFile(null);
    setLastFile(null);
    setBusy(true);
    try {
      const response = await uploadSchemaText(text);
      setSchema(response.schema_id, response.model, { kind: "text", content: text });
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
        const source: SchemaSource = { kind: "url", url: target };
        writeSourcePath(source);
        setSchema(response.schema_id, response.model, source);
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
        const source: SchemaSource = { kind: "release", tag: tagName, filename };
        writeSourcePath(source);
        setSchema(response.schema_id, response.model, source);
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
      void stageFiles(Array.from(event.dataTransfer.files ?? []));
    },
    [stageFiles],
  );

  // A shared link (`/url?src=…`, `/fundsxml?release=…&file=…`) loads its
  // source straight away; the tab switch below keeps the query intact.
  const autoLoaded = useRef(false);
  useEffect(() => {
    if (autoLoaded.current) return;
    autoLoaded.current = true;
    const source = sourceFromLocation();
    if (!source) return;
    if (source.kind === "url") {
      setUrl(source.url);
      void loadFromUrl(source.url);
    } else if (source.kind === "release") {
      void loadFromRelease(source.tag, source.filename);
    }
  }, [loadFromUrl, loadFromRelease]);

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
            multiple
            className="hidden"
            onChange={(e) => {
              void stageFiles(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
          <p className="mb-4 text-slate-700 dark:text-slate-300">
            {coarsePointer
              ? "Choose a file to load."
              : "Drop a file here, or click the button to choose one."}
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
          >
            Choose files…
          </button>
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
            Multi-file schemas: drop the <code>.xsd</code> files together, or a ZIP containing
            them. You will be asked which one is the main schema.
          </p>
          {staged && (
            <div className="mt-4 text-left panel rounded-md p-3 border border-slate-200 dark:border-slate-700">
              <p className="text-sm text-slate-700 dark:text-slate-300 mb-2">
                {staged.kind === "zip"
                  ? `${staged.files[0].name} contains ${staged.candidates.length} schemas.`
                  : `${staged.files.length} files chosen, ${staged.candidates.length} of them schemas.`}{" "}
                Which one is the main schema?
              </p>
              <label className="block text-xs text-slate-500 dark:text-slate-400">
                Main schema
                <select
                  className="block w-full mt-1 px-2 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100"
                  value={staged.main}
                  onChange={(e) => setStaged({ ...staged, main: e.target.value })}
                >
                  {staged.candidates.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void upload(staged.files, staged.main)}
                >
                  Load
                </button>
                <button type="button" className="btn" disabled={busy} onClick={() => setStaged(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
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
          onUploadAnyway={pendingFile ? () => void upload([pendingFile], undefined, { force: true }) : undefined}
        />
      )}
    </div>
  );
}
