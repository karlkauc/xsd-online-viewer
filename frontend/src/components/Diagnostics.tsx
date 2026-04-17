import { useState } from "react";
import { useSelection } from "../stores/selectionStore";

export function Diagnostics() {
  const model = useSelection((s) => s.model);
  const [collapsed, setCollapsed] = useState(false);
  const diagnostics = model?.diagnostics ?? [];
  if (diagnostics.length === 0) return null;
  return (
    <aside className="border-b border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200 text-sm">
      <button
        type="button"
        className="w-full text-left px-4 py-1.5 font-medium"
        onClick={() => setCollapsed((c) => !c)}
      >
        {collapsed ? "▸" : "▾"} {diagnostics.length} diagnostic{diagnostics.length === 1 ? "" : "s"}
      </button>
      {!collapsed && (
        <ul className="px-4 pb-2 space-y-0.5 text-xs">
          {diagnostics.map((d, i) => (
            <li key={i}>
              <strong className="uppercase">{d.severity}:</strong> {d.message}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
