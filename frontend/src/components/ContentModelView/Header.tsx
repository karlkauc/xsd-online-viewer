import type { NodeIndexEntry, ComplexType, ElementDecl, SimpleType } from "../../types/schema";
import { KindBadge } from "../TreeView/KindBadge";

interface HeaderProps {
  entry: NodeIndexEntry;
  onSelectBase?: (qname: string) => void;
}

function typeLine(entry: NodeIndexEntry): string {
  const node = entry.node;
  if (entry.kind === "element") {
    const e = node as ElementDecl;
    if (e.type_name) return `→ ${e.type_name}`;
    if (e.type_inline_complex) return "→ (inline complex type)";
    if (e.type_inline_simple) return "→ (inline simple type)";
    return "→ (anyType)";
  }
  if (entry.kind === "complexType") {
    const c = node as ComplexType;
    return `complexType · ${c.content_kind} content`;
  }
  if (entry.kind === "simpleType") {
    const s = node as SimpleType;
    return `simpleType · ${s.derivation}${s.base ? ` of ${s.base}` : ""}`;
  }
  if (entry.kind === "group") return "model group";
  if (entry.kind === "attributeGroup") return "attribute group";
  if (entry.kind === "attribute") return "attribute";
  return "";
}

function extendsBase(entry: NodeIndexEntry): string | null {
  if (entry.kind !== "complexType") return null;
  const c = entry.node as ComplexType;
  if (c.derivation === "extension" && c.base) return c.base;
  return null;
}

export function Header({ entry, onSelectBase }: HeaderProps) {
  const base = extendsBase(entry);
  return (
    <header className="px-6 pt-6 pb-4 border-b border-slate-200 dark:border-slate-800">
      <div className="flex items-center gap-2">
        <KindBadge kind={entry.kind} />
        <h2 className="font-mono text-lg">{entry.label}</h2>
      </div>
      {entry.qname && (
        <p className="mt-1 text-xs font-mono text-slate-500 dark:text-slate-400 break-all">
          {entry.qname}
        </p>
      )}
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 font-mono">{typeLine(entry)}</p>
      {base && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          extends{" "}
          <button
            type="button"
            className="font-mono text-accent hover:underline"
            onClick={() => onSelectBase?.(base)}
          >
            {base}
          </button>
          {" "}— see base for inherited members.
        </p>
      )}
    </header>
  );
}
