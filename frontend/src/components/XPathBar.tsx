import { useMemo } from "react";
import { useSelection } from "../stores/selectionStore";
import { computeXPath } from "../lib/xpath";
import { CopyButton } from "./CopyButton";

export function XPathBar() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
  const parentById = useSelection((s) => s.parentById);
  const selectAndReveal = useSelection((s) => s.selectAndReveal);

  const segments = useMemo(
    () => computeXPath(selectedId, indexById, parentById),
    [selectedId, indexById, parentById],
  );

  if (!segments || segments.length === 0) return null;

  // Expands the ancestors of the clicked step so the tree and diagram can
  // show it (lib/revealPath.ts), then selects it.
  const onClickSegment = (idx: number) => selectAndReveal(segments[idx].id);

  return (
    <nav
      aria-label="XPath"
      title="Document-instance XPath of the selected node; click a step to select it"
      className="mt-2 flex items-start gap-1 min-w-0"
    >
      <div className="flex flex-wrap items-center gap-y-0.5 min-w-0 text-[11px] font-mono leading-snug text-slate-500 dark:text-slate-400">
        <span className="text-slate-400 dark:text-slate-500">/</span>
        {segments.map((seg, idx) => {
          const isLast = idx === segments.length - 1;
          return (
            <span key={`${seg.id}:${idx}`} className="flex items-center">
              <button
                type="button"
                onClick={() => onClickSegment(idx)}
                title={seg.label}
                className={
                  "px-0.5 rounded break-all text-left hover:bg-slate-200 dark:hover:bg-slate-800 " +
                  (isLast
                    ? "text-slate-900 dark:text-slate-100 font-semibold"
                    : "text-slate-500 dark:text-slate-400")
                }
              >
                {seg.label}
              </button>
              {!isLast && (
                <span className="text-slate-400 dark:text-slate-500">/</span>
              )}
            </span>
          );
        })}
      </div>
      <CopyButton
        className="-mt-0.5 shrink-0"
        label="Copy XPath"
        text={() => "/" + segments.map((seg) => seg.label).join("/")}
      />
    </nav>
  );
}
