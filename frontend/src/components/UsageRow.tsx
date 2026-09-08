import type { NodeIndexEntry } from "../types/schema";
import { KindBadge } from "./TreeView/KindBadge";

// A single row in the "Used by" / usage lists — a clickable chip that jumps
// selection to the referencing node.
export function UsageRow({ entry, onClick }: { entry: NodeIndexEntry; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left group hover:bg-slate-100 dark:hover:bg-slate-800/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors"
    >
      <KindBadge kind={entry.kind} />
      <span className="font-mono text-[12.5px] truncate flex-1 text-slate-800 dark:text-slate-100">
        {entry.label}
      </span>
      <span
        className="text-slate-300 dark:text-slate-600 group-hover:text-accent group-hover:translate-x-0.5 transition-all"
        aria-hidden="true"
      >
        →
      </span>
    </button>
  );
}
