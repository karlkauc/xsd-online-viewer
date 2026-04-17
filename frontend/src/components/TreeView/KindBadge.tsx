import type { SchemaNodeKind } from "../../types/schema";

const COLORS: Record<SchemaNodeKind, string> = {
  element: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  attribute: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  complexType: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  simpleType: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  group: "bg-pink-100 text-pink-800 dark:bg-pink-900/40 dark:text-pink-300",
  attributeGroup: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
};

const LABELS: Record<SchemaNodeKind, string> = {
  element: "E",
  attribute: "A",
  complexType: "CT",
  simpleType: "ST",
  group: "G",
  attributeGroup: "AG",
};

export function KindBadge({ kind }: { kind: SchemaNodeKind }) {
  return (
    <span className={`chip ${COLORS[kind]}`} title={kind}>
      {LABELS[kind]}
    </span>
  );
}
