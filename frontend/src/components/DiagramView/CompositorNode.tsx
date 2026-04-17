import { Handle, Position } from "@xyflow/react";

interface CompositorData {
  kind: "sequence" | "choice" | "all" | "any" | "group-ref";
  label: string;
}

const BG: Record<CompositorData["kind"], string> = {
  sequence: "bg-slate-200 dark:bg-slate-700",
  choice: "bg-amber-200 dark:bg-amber-800",
  all: "bg-emerald-200 dark:bg-emerald-800",
  any: "bg-fuchsia-200 dark:bg-fuchsia-800",
  "group-ref": "bg-pink-200 dark:bg-pink-800",
};

export function CompositorNode({ data }: { data: CompositorData }) {
  return (
    <div
      className={`rounded-md px-2 py-1 font-mono text-xs text-slate-900 dark:text-slate-100 ${BG[data.kind]}`}
      style={{ width: 70, textAlign: "center" }}
    >
      <Handle type="target" position={Position.Left} />
      {data.label}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
