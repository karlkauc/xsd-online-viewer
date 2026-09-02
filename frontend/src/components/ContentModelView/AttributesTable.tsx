import { useMemo } from "react";
import type { AttributeDecl, AttributeGroup, NodeIndexEntry } from "../../types/schema";
import { useSelection } from "../../stores/selectionStore";
import { resolveReference } from "../../lib/indexSchema";
import { TapToReveal } from "../TapToReveal";

interface AttributesTableProps {
  /** Attributes declared directly on the node. */
  attributes: AttributeDecl[];
  /** Attribute-group QNames to resolve and inline. */
  attributeGroupRefs: string[];
}

interface ResolvedAttribute {
  attr: AttributeDecl;
  /** Origin label when the attribute was pulled in via a referenced group. */
  origin: string | null;
}

function collectFromGroup(
  ref: string,
  index: NodeIndexEntry[],
  seen: Set<string>,
  out: ResolvedAttribute[],
): void {
  const entry = resolveReference(ref, index, ["attributeGroup"]);
  if (!entry) return;
  if (seen.has(entry.id)) return;
  seen.add(entry.id);
  const ag = entry.node as AttributeGroup;
  for (const a of ag.attributes) out.push({ attr: a, origin: entry.label });
  for (const nested of ag.attribute_group_refs) {
    collectFromGroup(nested, index, seen, out);
  }
}

function firstDocLine(attr: AttributeDecl): string {
  const text = attr.annotation?.documentation?.[0]?.text?.trim() ?? "";
  if (!text) return "";
  return text.split(/\r?\n/)[0];
}

function defOrFix(attr: AttributeDecl): string {
  if (attr.fixed != null) return `[fixed] ${attr.fixed}`;
  if (attr.default != null) return attr.default;
  return "—";
}

export function AttributesTable({ attributes, attributeGroupRefs }: AttributesTableProps) {
  const index = useSelection((s) => s.index);
  const setSelected = useSelection((s) => s.setSelected);

  const rows = useMemo<ResolvedAttribute[]>(() => {
    const out: ResolvedAttribute[] = attributes.map((a) => ({ attr: a, origin: null }));
    const seen = new Set<string>();
    for (const ref of attributeGroupRefs) {
      collectFromGroup(ref, index, seen, out);
    }
    return out;
  }, [attributes, attributeGroupRefs, index]);

  if (!rows.length) return null;

  const onTypeClick = (typeName: string | null) => {
    if (!typeName) return;
    const entry = resolveReference(typeName, index, ["simpleType"]);
    if (entry) setSelected(entry.id);
  };

  return (
    <section className="px-4 md:px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        Attributes
      </h3>
      <div className="overflow-x-auto">
      <table className="w-full min-w-[20rem] md:min-w-0 text-sm border-collapse">
        <thead>
          <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
            <th className="py-1.5 pr-3 font-semibold">Name</th>
            <th className="py-1.5 pr-3 font-semibold">Type</th>
            <th className="py-1.5 pr-3 font-semibold">Use</th>
            <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">Default / Fixed</th>
            <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">Doc</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ attr, origin }, i) => {
            const doc = firstDocLine(attr);
            return (
              <tr
                key={`${attr.id}-${i}`}
                className="border-b border-slate-100 dark:border-slate-900 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                onClick={() => setSelected(attr.id)}
              >
                <td className="py-1.5 pr-3 font-mono">
                  @{attr.name ?? attr.ref ?? "?"}
                  {origin && (
                    <span className="ml-1 text-[10px] text-slate-400">from {origin}</span>
                  )}
                </td>
                <td className="py-1.5 pr-3 font-mono">
                  {attr.type_name ? (
                    <button
                      type="button"
                      className="text-accent hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onTypeClick(attr.type_name);
                      }}
                    >
                      {attr.type_name}
                    </button>
                  ) : attr.type_inline ? (
                    <span className="text-slate-500">(inline simple)</span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="py-1.5 pr-3">{attr.use}</td>
                <td className="py-1.5 pr-3 font-mono hidden md:table-cell">{defOrFix(attr)}</td>
                <td className="py-1.5 pr-3 text-slate-600 dark:text-slate-400 text-xs max-w-[260px] hidden md:table-cell">
                  <TapToReveal summary={doc || ""} details={attr.annotation?.documentation?.[0]?.text} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </section>
  );
}
