import { useMemo } from "react";
import { Virtuoso } from "react-virtuoso";
import { useSelection } from "../../stores/selectionStore";
import type { SchemaNodeKind } from "../../types/schema";
import { buildTreeRows, type TreeRow } from "./treeRows";
import { KindBadge } from "./KindBadge";
import { treeIndentPx } from "./treeIndent";
import { SM_QUERY, useMediaQuery } from "../../lib/useMediaQuery";

const ALL_KINDS: SchemaNodeKind[] = [
  "element",
  "complexType",
  "simpleType",
  "group",
  "attributeGroup",
  "attribute",
];

// Filter chips pick up the same hue as the kind's badge so the color system
// flows chip → tree badge → detail panel.
const KIND_CHIP_CLASS: Record<SchemaNodeKind, string> = {
  element:
    "bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800/50",
  attribute:
    "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800/50",
  complexType:
    "bg-violet-100 text-violet-800 border-violet-200 dark:bg-violet-900/40 dark:text-violet-300 dark:border-violet-800/50",
  simpleType:
    "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-800/50",
  group:
    "bg-pink-100 text-pink-800 border-pink-200 dark:bg-pink-900/40 dark:text-pink-300 dark:border-pink-800/50",
  attributeGroup:
    "bg-rose-100 text-rose-800 border-rose-200 dark:bg-rose-900/40 dark:text-rose-300 dark:border-rose-800/50",
};

function occursPillClass(occurs: string): string {
  if (occurs.startsWith("0")) {
    return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
  }
  if (occurs.includes("∞")) {
    return "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300";
  }
  return "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400";
}

export function TreeView() {
  const model = useSelection((s) => s.model);
  const indexById = useSelection((s) => s.indexById);
  const selectedId = useSelection((s) => s.selectedId);
  const expandedIds = useSelection((s) => s.expandedIds);
  const filterKinds = useSelection((s) => s.filterKinds);
  const setSelected = useSelection((s) => s.setSelected);
  const toggleExpanded = useSelection((s) => s.toggleExpanded);
  const setFilterKinds = useSelection((s) => s.setFilterKinds);

  const rows = useMemo<TreeRow[]>(() => {
    if (!model) return [];
    return buildTreeRows(model, expandedIds, filterKinds, indexById);
  }, [model, expandedIds, filterKinds, indexById]);

  const totalNodes = indexById.size;
  const compact = !useMediaQuery(SM_QUERY);

  const toggleKind = (kind: SchemaNodeKind) => {
    const next = new Set(filterKinds);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    setFilterKinds(next);
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Structure
        </span>
        <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500">
          {totalNodes} nodes · {rows.length} visible
        </span>
      </div>
      <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800">
        <div className="flex gap-1 overflow-x-auto sm:flex-wrap">
          {ALL_KINDS.map((kind) => {
            const active = filterKinds.has(kind);
            return (
              <button
                key={kind}
                type="button"
                className={
                  "chip border inline-flex items-center gap-1 cursor-pointer transition-opacity shrink-0 touch:py-1 " +
                  KIND_CHIP_CLASS[kind] +
                  (active ? "" : " opacity-40 line-through")
                }
                onClick={() => toggleKind(kind)}
                title={`Toggle ${kind}`}
              >
                {kind}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <Virtuoso
          style={{ height: "100%" }}
          totalCount={rows.length}
          itemContent={(idx) => {
            const row = rows[idx];
            const active = selectedId === row.id;
            return (
              <div
                className={
                  "flex items-center gap-1 cursor-pointer select-none text-sm touch:py-1 " +
                  "border-l-2 " +
                  (active
                    ? "bg-blue-50 dark:bg-blue-900/30 border-accent"
                    : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-900")
                }
                style={{ paddingLeft: `${treeIndentPx(row.depth, compact)}px`, paddingRight: 8 }}
                role="treeitem"
                aria-selected={active}
                aria-expanded={row.hasChildren ? expandedIds.has(row.id) : undefined}
                onClick={() => setSelected(row.id)}
              >
                {row.hasChildren ? (
                  <button
                    type="button"
                    aria-label={expandedIds.has(row.id) ? "Collapse" : "Expand"}
                    className="px-1 touch:px-2 touch:py-1 text-slate-500"
                    onClick={(event) => {
                      event.stopPropagation();
                      toggleExpanded(row.id);
                    }}
                  >
                    {expandedIds.has(row.id) ? "▾" : "▸"}
                  </button>
                ) : (
                  <span className="inline-block w-5" />
                )}
                <KindBadge kind={row.kind} />
                <span className="font-mono truncate py-0.5">{row.label}</span>
                {row.occurs && (
                  <span
                    className={
                      "ml-1 px-1.5 py-px rounded text-[10px] font-mono tabular-nums " +
                      occursPillClass(row.occurs)
                    }
                    title={`occurs ${row.occurs}`}
                  >
                    {row.occurs}
                  </span>
                )}
                {row.typeHint && (
                  <span className="hidden sm:inline ml-1 text-xs font-mono text-slate-500 dark:text-slate-400 truncate">
                    : {row.typeHint}
                  </span>
                )}
              </div>
            );
          }}
        />
      </div>
    </div>
  );
}
