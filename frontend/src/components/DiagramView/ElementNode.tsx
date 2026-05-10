import { Handle, Position } from "@xyflow/react";
import clsx from "clsx";

interface ElementNodeData {
  schemaId: string;
  label: string;
  type?: string | null;
  occurs?: string | null;
  expandable?: boolean;
  expanded?: boolean;
  selected?: boolean;
  attributes?: { id: string; name: string | null; type_name: string | null }[];
  documentationLines?: string[];
  documentationFull?: string | null;
  assertCount?: number;
  alternativesCount?: number;
}

export function ElementNode({ data }: { data: ElementNodeData }) {
  const attrs = data.attributes ?? [];
  const docLines = data.documentationLines ?? [];

  return (
    <div
      className={clsx(
        "rounded-md border bg-white dark:bg-slate-900 shadow-sm text-xs",
        data.selected
          ? "border-accent ring-2 ring-accent/50"
          : "border-slate-300 dark:border-slate-700",
      )}
      style={{ width: 220 }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center justify-between gap-1 px-2 py-1 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800">
        <span className="font-mono font-semibold truncate">{data.label}</span>
        <span className="flex items-center gap-1 shrink-0">
          {data.alternativesCount && data.alternativesCount > 0 ? (
            <span
              className="inline-flex items-center gap-0.5 px-1 rounded text-[9.5px] font-mono font-medium border bg-violet-50 text-violet-800 border-violet-200 dark:bg-violet-900/30 dark:text-violet-200 dark:border-violet-800/60"
              title={`${data.alternativesCount} XSD 1.1 type alternative${data.alternativesCount === 1 ? "" : "s"}`}
            >
              ≷ {data.alternativesCount}
            </span>
          ) : null}
          {data.assertCount && data.assertCount > 0 ? (
            <span
              className="inline-flex items-center gap-0.5 px-1 rounded text-[9.5px] font-mono font-medium border bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-800/60"
              title={`${data.assertCount} XSD 1.1 assertion${data.assertCount === 1 ? "" : "s"}`}
            >
              ⚖ {data.assertCount}
            </span>
          ) : null}
          {data.occurs && <span className="text-[10px] text-slate-500">{data.occurs}</span>}
        </span>
      </div>
      <div className="px-2 py-1 font-mono text-[11px] text-slate-500 dark:text-slate-400 truncate">
        {data.type ?? "anonymous"}
      </div>

      {attrs.length > 0 && (
        <ul className="border-t border-slate-200 dark:border-slate-800 px-2 py-1 space-y-0.5">
          {attrs.slice(0, 4).map((attr) => (
            <li key={attr.id} className="font-mono text-[10px] truncate">
              <span className="text-amber-700 dark:text-amber-300">@{attr.name}</span>
              {attr.type_name && <span className="text-slate-500"> : {attr.type_name}</span>}
            </li>
          ))}
          {attrs.length > 4 && (
            <li className="text-[10px] text-slate-500">+{attrs.length - 4} more…</li>
          )}
        </ul>
      )}

      {docLines.length > 0 && (
        <div
          className="border-t border-slate-200 dark:border-slate-800 px-2 py-1 text-[10px] italic text-slate-500 dark:text-slate-400 leading-snug"
          title={data.documentationFull ?? undefined}
        >
          {docLines.map((line, i) => (
            <div key={i} className="truncate">
              {line}
            </div>
          ))}
        </div>
      )}

      {data.expandable && (
        <div className="px-2 py-0.5 text-[10px] text-accent border-t border-slate-200 dark:border-slate-800 text-right">
          {data.expanded ? "click to collapse" : "click to expand"}
        </div>
      )}
      {/* The right-side source handle only appears when the node has
          something to connect to — so leaves are visually distinct from
          expandable nodes. */}
      {data.expandable && <Handle type="source" position={Position.Right} />}
    </div>
  );
}
