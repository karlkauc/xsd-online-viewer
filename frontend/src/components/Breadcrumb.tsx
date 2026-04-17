import { useSelection } from "../stores/selectionStore";

export function Breadcrumb() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
  const setSelected = useSelection((s) => s.setSelected);
  const entry = selectedId ? indexById.get(selectedId) : undefined;
  if (!entry) return null;
  return (
    <nav className="text-xs font-mono text-slate-500 dark:text-slate-400 flex items-center gap-1 truncate">
      <button
        type="button"
        onClick={() => setSelected(null)}
        className="hover:text-slate-900 dark:hover:text-slate-100"
      >
        schema
      </button>
      <span>›</span>
      <span className="text-slate-700 dark:text-slate-200 truncate">{entry.label}</span>
    </nav>
  );
}
