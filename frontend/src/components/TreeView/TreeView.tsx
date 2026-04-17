import { useMemo } from "react";
import { Virtuoso } from "react-virtuoso";
import { useSelection } from "../../stores/selectionStore";
import type { SchemaNodeKind } from "../../types/schema";
import { buildTreeRows, type TreeRow } from "./treeRows";
import { KindBadge } from "./KindBadge";

const ALL_KINDS: SchemaNodeKind[] = [
  "element",
  "complexType",
  "simpleType",
  "group",
  "attributeGroup",
  "attribute",
];

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

  const toggleKind = (kind: SchemaNodeKind) => {
    const next = new Set(filterKinds);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    setFilterKinds(next);
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800">
        <div className="flex flex-wrap gap-1">
          {ALL_KINDS.map((kind) => {
            const active = filterKinds.has(kind);
            return (
              <button
                key={kind}
                type="button"
                className={
                  "chip border " +
                  (active
                    ? "bg-slate-200 dark:bg-slate-700 border-slate-300 dark:border-slate-600"
                    : "bg-transparent border-slate-200 dark:border-slate-800 text-slate-400 line-through")
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
                  "flex items-center gap-1 cursor-pointer select-none text-sm " +
                  "border-l-2 " +
                  (active
                    ? "bg-blue-50 dark:bg-blue-900/30 border-accent"
                    : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-900")
                }
                style={{ paddingLeft: `${row.depth * 14 + 6}px`, paddingRight: 8 }}
                role="treeitem"
                aria-selected={active}
                aria-expanded={row.hasChildren ? expandedIds.has(row.id) : undefined}
                onClick={() => setSelected(row.id)}
              >
                {row.hasChildren ? (
                  <button
                    type="button"
                    aria-label={expandedIds.has(row.id) ? "Collapse" : "Expand"}
                    className="px-1 text-slate-500"
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
                  <span className="text-xs text-slate-500 dark:text-slate-400">{row.occurs}</span>
                )}
                {row.typeHint && (
                  <span className="ml-1 text-xs font-mono text-slate-500 dark:text-slate-400 truncate">
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
