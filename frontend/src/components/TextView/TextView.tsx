import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { xml } from "@codemirror/lang-xml";
import { EditorView } from "@codemirror/view";
import { useSelection } from "../../stores/selectionStore";

const isDark = () => document.documentElement.classList.contains("dark");

export function TextView() {
  const model = useSelection((s) => s.model);
  const schemaId = useSelection((s) => s.schemaId);
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);

  const viewRef = useRef<EditorView | null>(null);
  const [activeFileId, setActiveFileId] = useState<string | null>(
    () => model?.files[0]?.id ?? null,
  );

  const activeFile = useMemo(
    () => model?.files.find((f) => f.id === activeFileId) ?? model?.files[0],
    [model, activeFileId],
  );

  // If the selection points into another file, switch the tab so the
  // highlight is visible. Keeps Tree/Diagram ↔ Text selection in lock-step.
  useEffect(() => {
    if (!selectedId) return;
    const entry = indexById.get(selectedId);
    const fileId = entry?.source_ref?.file_id;
    if (fileId && fileId !== activeFileId) setActiveFileId(fileId);
  }, [selectedId, indexById, activeFileId]);

  const targetLine = useMemo(() => {
    if (!selectedId) return null;
    const entry = indexById.get(selectedId);
    if (!entry?.source_ref) return null;
    if (entry.source_ref.file_id !== activeFile?.id) return null;
    return entry.source_ref.line ?? null;
  }, [selectedId, indexById, activeFile]);

  const scrollToLine = useCallback((view: EditorView, line: number) => {
    const clamped = Math.max(1, Math.min(line, view.state.doc.lines));
    const docLine = view.state.doc.line(clamped);
    view.dispatch({
      selection: { anchor: docLine.from },
      effects: EditorView.scrollIntoView(docLine.from, { y: "start" }),
    });
  }, []);

  // Re-scroll whenever the target line changes — covers the case where the
  // user switches tab, changes selection via the search palette, or clicks a
  // Find Usages link while the Text tab is already visible.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || targetLine == null) return;
    scrollToLine(view, targetLine);
  }, [targetLine, scrollToLine]);

  if (!model || !activeFile) return null;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-2 py-1 border-b border-slate-200 dark:border-slate-800 overflow-x-auto">
        {model.files.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setActiveFileId(f.id)}
            className={
              "px-2 py-1 text-xs font-mono rounded " +
              (f.id === activeFile.id
                ? "bg-accent text-white dark:bg-accent-dark dark:text-slate-950"
                : "hover:bg-slate-100 dark:hover:bg-slate-800")
            }
            title={f.filename}
          >
            {f.filename.split("/").pop()}
          </button>
        ))}
        {schemaId && activeFile.content && (
          <a
            className="btn ml-auto text-xs"
            href={`/api/schema/${schemaId}/file/${activeFile.id}/formatted`}
          >
            Download formatted
          </a>
        )}
      </div>
      <div className="flex-1 min-h-0">
        <CodeMirror
          value={activeFile.content ?? ""}
          extensions={[xml(), EditorView.lineWrapping]}
          editable={false}
          theme={isDark() ? "dark" : "light"}
          height="100%"
          onCreateEditor={(view) => {
            viewRef.current = view;
            if (targetLine != null) scrollToLine(view, targetLine);
          }}
        />
      </div>
    </div>
  );
}
