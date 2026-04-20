import { useMemo } from "react";
import { useSelection } from "../stores/selectionStore";
import { KindBadge } from "./TreeView/KindBadge";

export function Breadcrumb() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
  const parentById = useSelection((s) => s.parentById);
  const setSelected = useSelection((s) => s.setSelected);

  const path = useMemo(() => {
    if (!selectedId) return [];
    const out: string[] = [];
    let cur: string | undefined = selectedId;
    // `seen` guards against cyclic schemas (possible via xs:extension chains)
    // where parentById would otherwise loop back on itself.
    const seen = new Set<string>();
    while (cur && !seen.has(cur)) {
      seen.add(cur);
      out.unshift(cur);
      cur = parentById.get(cur);
    }
    return out;
  }, [selectedId, parentById]);

  if (!path.length) {
    return (
      <nav className="text-xs font-mono text-slate-400 truncate">
        <button
          type="button"
          onClick={() => setSelected(null)}
          className="hover:text-slate-600 dark:hover:text-slate-200"
        >
          schema
        </button>
        <span className="ml-1 text-slate-300 dark:text-slate-600">· no selection</span>
      </nav>
    );
  }

  return (
    <nav className="text-xs font-mono text-slate-500 dark:text-slate-400 flex items-center gap-1 truncate min-w-0">
      <button
        type="button"
        onClick={() => setSelected(null)}
        className="hover:text-slate-900 dark:hover:text-slate-100 shrink-0"
      >
        schema
      </button>
      {path.map((id, i) => {
        const entry = indexById.get(id);
        if (!entry) return null;
        const isLast = i === path.length - 1;
        return (
          <span key={id} className="flex items-center gap-1 min-w-0">
            <span className="text-slate-300 dark:text-slate-600 shrink-0">›</span>
            <button
              type="button"
              onClick={() => setSelected(id)}
              className={
                "flex items-center gap-1 px-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 truncate " +
                (isLast ? "text-slate-900 dark:text-slate-100 font-semibold" : "")
              }
              title={entry.qname ?? entry.label}
            >
              <KindBadge kind={entry.kind} />
              <span className="truncate">{entry.label}</span>
            </button>
          </span>
        );
      })}
    </nav>
  );
}
