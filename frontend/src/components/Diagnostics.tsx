import { useSelection } from "../stores/selectionStore";

export function Diagnostics() {
  const model = useSelection((s) => s.model);
  const visible = useSelection((s) => s.diagnosticsVisible);
  const setVisible = useSelection((s) => s.setDiagnosticsVisible);
  const diagnostics = model?.diagnostics ?? [];
  if (diagnostics.length === 0 || !visible) return null;
  return (
    <aside className="border-b border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200 text-sm">
      <div className="flex items-start justify-between gap-2 px-4 py-1.5">
        <span className="font-medium">
          {diagnostics.length} diagnostic{diagnostics.length === 1 ? "" : "s"}
        </span>
        <button
          type="button"
          className="shrink-0 inline-flex items-center justify-center w-6 h-6 rounded hover:bg-amber-100 dark:hover:bg-amber-900/40 text-amber-900 dark:text-amber-200"
          onClick={() => setVisible(false)}
          title="Hide diagnostics"
          aria-label="Hide diagnostics"
        >
          <span aria-hidden="true" className="text-base leading-none">×</span>
        </button>
      </div>
      <ul className="px-4 pb-2 space-y-0.5 text-xs">
        {diagnostics.map((d, i) => (
          <li key={i}>
            <strong className="uppercase">{d.severity}:</strong> {d.message}
          </li>
        ))}
      </ul>
    </aside>
  );
}
