import { useMemo } from "react";
import { useSelection } from "../stores/selectionStore";
import { computeXPath, type XPathSegment } from "../lib/xpath";
import { CopyButton } from "./CopyButton";

// Collects all IDs that must be expanded in the tree so that navigating to
// `targetIdx` reveals its row. Each XPath segment is the id of an element
// (or attribute leaf), but the tree descent passes through the enclosing
// named complexType too — we add each element's direct `parentById` entry
// to cover that (treeRows.ts resolves type references on the fly when
// expanding, so the intermediate complexType must be expanded as well).
function collectExpansionIds(
  segments: XPathSegment[],
  targetIdx: number,
  parentById: Map<string, string>,
): string[] {
  const ids = new Set<string>();
  for (let i = 0; i < targetIdx; i++) {
    const seg = segments[i];
    ids.add(seg.id);
    const parent = parentById.get(seg.id);
    if (parent) ids.add(parent);
  }
  // For attribute targets, expand the parent element too.
  const target = segments[targetIdx];
  if (target?.isAttribute && targetIdx > 0) {
    ids.add(segments[targetIdx - 1].id);
  }
  return Array.from(ids);
}

export function XPathBar() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
  const parentById = useSelection((s) => s.parentById);
  const setSelected = useSelection((s) => s.setSelected);
  const setExpanded = useSelection((s) => s.setExpanded);

  const segments = useMemo(
    () => computeXPath(selectedId, indexById, parentById),
    [selectedId, indexById, parentById],
  );

  if (!segments || segments.length === 0) return null;

  const onClickSegment = (idx: number) => {
    const target = segments[idx];
    const toExpand = collectExpansionIds(segments, idx, parentById);
    for (const id of toExpand) setExpanded(id, true);
    setSelected(target.id);
  };

  return (
    <nav
      aria-label="XPath"
      className="flex items-center gap-0.5 px-3 py-1.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-xs font-mono text-slate-600 dark:text-slate-300 overflow-x-auto whitespace-nowrap"
    >
      <span className="text-slate-400 dark:text-slate-500 shrink-0">/</span>
      {segments.map((seg, idx) => {
        const isLast = idx === segments.length - 1;
        return (
          <span key={`${seg.id}:${idx}`} className="flex items-center">
            <button
              type="button"
              onClick={() => onClickSegment(idx)}
              title={seg.label}
              className={
                "px-1 rounded hover:bg-slate-200 dark:hover:bg-slate-800 " +
                (isLast
                  ? "text-slate-900 dark:text-slate-100 font-semibold"
                  : "text-slate-600 dark:text-slate-300")
              }
            >
              {seg.label}
            </button>
            {!isLast && (
              <span className="text-slate-400 dark:text-slate-500 shrink-0">/</span>
            )}
          </span>
        );
      })}
      <CopyButton
        className="ml-1 shrink-0"
        label="Copy XPath"
        text={() => "/" + segments.map((seg) => seg.label).join("/")}
      />
    </nav>
  );
}
