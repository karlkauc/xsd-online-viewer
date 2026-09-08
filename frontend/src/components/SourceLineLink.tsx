import { useSelection } from "../stores/selectionStore";
import type { SourceRef } from "../types/schema";

interface SourceLineLinkProps {
  sourceRef: SourceRef;
  className?: string;
}

// Small inline button rendering "file:line →" that jumps the Text tab to an
// arbitrary source location — used wherever a constraint's selector/field
// step, or an ID/IDREF candidate, carries its own source_ref distinct from
// the currently selected node's.
export function SourceLineLink({ sourceRef, className = "" }: SourceLineLinkProps) {
  const jumpToSource = useSelection((s) => s.jumpToSource);
  return (
    <button
      type="button"
      onClick={() => jumpToSource(sourceRef)}
      title="Open in the Text tab"
      className={
        "inline-flex items-center gap-1 font-mono text-[11px] text-slate-500 hover:text-accent dark:text-slate-400 dark:hover:text-accent-dark transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded " +
        className
      }
    >
      <code>
        {sourceRef.file_id}:{sourceRef.line}
      </code>
      <span aria-hidden="true">→</span>
    </button>
  );
}
