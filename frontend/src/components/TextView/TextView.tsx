import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { xml } from "@codemirror/lang-xml";
import { StateEffect, StateField } from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import { useSelection } from "../../stores/selectionStore";

const isDark = () => document.documentElement.classList.contains("dark");

// StateEffect/StateField driving a single full-line highlight for the
// currently-targeted source location. Dispatching `setHighlightedLine.of(n)`
// highlights line n; `of(null)` clears it.
const setHighlightedLine = StateEffect.define<number | null>();

const highlightedLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const e of tr.effects) {
      if (e.is(setHighlightedLine)) {
        if (e.value == null) return Decoration.none;
        const clamped = Math.max(1, Math.min(e.value, tr.state.doc.lines));
        const line = tr.state.doc.line(clamped);
        return Decoration.set([
          Decoration.line({ class: "cm-src-highlight" }).range(line.from),
        ]);
      }
    }
    return deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

const extensions = [xml(), EditorView.lineWrapping, highlightedLineField];

export function TextView() {
  const model = useSelection((s) => s.model);
  const schemaId = useSelection((s) => s.schemaId);
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);

  const viewRef = useRef<EditorView | null>(null);
  const [viewReady, setViewReady] = useState(false);
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

  const attachView = useCallback((view: EditorView | null) => {
    viewRef.current = view;
    setViewReady(view != null);
  }, []);

  // Scroll to and highlight the target line. Deferred one animation frame so
  // that on fresh mount (user clicked "View in source" from another tab)
  // CodeMirror has finished its first measure cycle before we dispatch
  // scrollIntoView — otherwise it silently no-ops at the top.
  useEffect(() => {
    if (!viewReady) return;
    const view = viewRef.current;
    if (!view) return;
    const id = requestAnimationFrame(() => {
      if (targetLine == null) {
        view.dispatch({ effects: setHighlightedLine.of(null) });
        return;
      }
      const clamped = Math.max(1, Math.min(targetLine, view.state.doc.lines));
      const docLine = view.state.doc.line(clamped);
      view.dispatch({
        effects: [
          setHighlightedLine.of(clamped),
          EditorView.scrollIntoView(docLine.from, { y: "start", yMargin: 40 }),
        ],
      });
    });
    return () => cancelAnimationFrame(id);
  }, [targetLine, activeFile?.id, viewReady]);

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
          extensions={extensions}
          editable={false}
          theme={isDark() ? "dark" : "light"}
          height="100%"
          onCreateEditor={attachView}
        />
      </div>
    </div>
  );
}
