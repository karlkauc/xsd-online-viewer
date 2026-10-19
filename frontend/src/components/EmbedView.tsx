import { useEffect, useState } from "react";
import { ApiError, loadSchemaFromUrl } from "../api/client";
import { readHashSelection, writeHashSelection } from "../lib/deepLink";
import { useSelection } from "../stores/selectionStore";
import { DiagramView } from "./DiagramView/DiagramView";

// /embed?src=<schema url>#/id/<node> — the diagram alone, for an iframe on a
// documentation site. Only public URLs (the same rule as /url), no uploads; the
// server lets any site frame this route and no other (backend/app/spa.py).

const SITE = "https://www.xsd-viewer.online";

function schemaSrc(): string | null {
  const src = new URLSearchParams(window.location.search).get("src");
  return src && /^https?:\/\//i.test(src) ? src : null;
}

/** `?node=` is accepted as well as the hash, for embed codes written by hand. */
function initialNode(): string | null {
  return readHashSelection() ?? new URLSearchParams(window.location.search).get("node");
}

export function EmbedView() {
  const model = useSelection((s) => s.model);
  const selectedId = useSelection((s) => s.selectedId);
  const setSchema = useSelection((s) => s.setSchema);
  const setSelected = useSelection((s) => s.setSelected);
  const [error, setError] = useState<string | null>(null);
  const src = schemaSrc();

  useEffect(() => {
    if (!src) {
      setError("Add ?src= with the public http(s) URL of an XSD to embed it.");
      return;
    }
    let cancelled = false;
    loadSchemaFromUrl(src)
      .then((response) => {
        if (cancelled) return;
        setSchema(response.schema_id, response.model, { kind: "url", url: src });
        const node = initialNode();
        if (node) setSelected(node);
      })
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [src, setSchema, setSelected]);

  useEffect(() => {
    if (model) writeHashSelection(selectedId);
  }, [model, selectedId]);

  const name = src ? decodeURIComponent(src.split(/[?#]/)[0].split("/").pop() || src) : "";
  const fullView = src ? `${SITE}/url?src=${encodeURIComponent(src)}&utm_source=embed${window.location.hash}` : SITE;

  return (
    <div className="h-full flex flex-col bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="flex items-center gap-2 px-2 py-1 text-xs border-b border-slate-200 dark:border-slate-800">
        <span className="font-mono truncate min-w-0 flex-1" title={src ?? undefined}>
          {name}
        </span>
        <a className="text-accent hover:underline whitespace-nowrap" href={fullView} target="_blank" rel="noopener noreferrer">
          Open in XSD Viewer ↗
        </a>
      </div>
      <div className="flex-1 min-h-0">
        {model ? (
          <DiagramView />
        ) : (
          <p className="p-4 text-sm text-slate-500" role={error ? "alert" : "status"}>
            {error ?? "Loading schema…"}
          </p>
        )}
      </div>
      <a
        className="px-2 py-0.5 text-[10px] text-right text-slate-400 hover:underline border-t border-slate-100 dark:border-slate-900"
        href={`${SITE}/?utm_source=embed`}
        target="_blank"
        rel="noopener noreferrer"
      >
        Powered by xsd-viewer.online
      </a>
    </div>
  );
}
