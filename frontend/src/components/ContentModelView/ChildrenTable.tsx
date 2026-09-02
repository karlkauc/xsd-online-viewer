import type { Particle } from "../../types/schema";
import { flattenParticle } from "../../lib/particles";
import { useSelection } from "../../stores/selectionStore";
import { resolveElementRef, resolveReference } from "../../lib/indexSchema";
import { COMPOSITOR_GLYPH, GROUP_REF_GLYPH, WILDCARD_GLYPH } from "./symbols";
import { KindBadge } from "../TreeView/KindBadge";
import { TapToReveal } from "../TapToReveal";

interface ChildrenTableProps {
  particle: Particle | null;
}

const INDENT_PX = 16;

export function ChildrenTable({ particle }: ChildrenTableProps) {
  const index = useSelection((s) => s.index);
  const indexById = useSelection((s) => s.indexById);
  const setSelected = useSelection((s) => s.setSelected);
  const rows = flattenParticle(particle);

  if (!rows.length) {
    return (
      <section className="px-6 py-4 text-sm text-slate-500 dark:text-slate-400">
        No child elements declared.
      </section>
    );
  }

  const onTypeClick = (typeName: string | null) => {
    if (!typeName) return;
    const entry =
      resolveReference(typeName, index, ["complexType"]) ??
      resolveReference(typeName, index, ["simpleType"]) ??
      resolveReference(typeName, index, ["element"]);
    if (entry) setSelected(entry.id);
  };

  const onGroupClick = (groupRef: string) => {
    const entry = resolveReference(groupRef, index, ["group"]);
    if (entry) setSelected(entry.id);
  };

  return (
    <section className="px-4 md:px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        Children
      </h3>
      {/* Seven columns never fit a phone; scroll the table, not the page. */}
      <div className="overflow-x-auto">
      <table className="w-full min-w-[28rem] md:min-w-0 text-sm border-collapse">
        <thead>
          <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
            <th className="py-1.5 pr-2 w-6"></th>
            <th className="py-1.5 pr-3 font-semibold">Name</th>
            <th className="py-1.5 pr-3 font-semibold">Kind</th>
            <th className="py-1.5 pr-3 font-semibold">Type</th>
            <th className="py-1.5 pr-3 font-semibold">Card.</th>
            <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">Default / Fixed</th>
            <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">Doc</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const padLeft = row.depth * INDENT_PX;

            // Compositor header row
            if (row.compositor) {
              return (
                <tr
                  key={row.key}
                  className="border-b border-slate-100 dark:border-slate-900 bg-slate-50/40 dark:bg-slate-900/30"
                >
                  <td className="py-1 pr-2 text-center text-slate-500" style={{ paddingLeft: padLeft }}>
                    {COMPOSITOR_GLYPH[row.compositor]}
                  </td>
                  <td className="py-1 pr-3 font-mono text-xs uppercase tracking-wide text-slate-500">
                    {row.compositor}
                  </td>
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3 font-mono text-xs text-slate-500">{row.occurs}</td>
                  <td className="py-1 pr-3 hidden md:table-cell" />
                  <td className="py-1 pr-3 hidden md:table-cell" />
                </tr>
              );
            }

            // Ellipsis row
            if (row.ellipsis !== undefined) {
              return (
                <tr key={row.key} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-1 pr-2 text-center text-slate-400" style={{ paddingLeft: padLeft }}>
                    …
                  </td>
                  <td colSpan={6} className="py-1 pr-3 text-xs text-slate-500 italic">
                    <TapToReveal summary="deeper sub-tree" details={row.ellipsis} className="font-mono" />
                  </td>
                </tr>
              );
            }

            // group-ref row
            if (row.groupRef) {
              return (
                <tr
                  key={row.key}
                  className="border-b border-slate-100 dark:border-slate-900 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                  onClick={() => onGroupClick(row.groupRef!)}
                >
                  <td className="py-1.5 pr-2 text-center text-slate-500" style={{ paddingLeft: padLeft }}>
                    {GROUP_REF_GLYPH}
                  </td>
                  <td className="py-1.5 pr-3 font-mono">
                    «{row.groupRef}»
                  </td>
                  <td className="py-1.5 pr-3"><KindBadge kind="group" /></td>
                  <td className="py-1.5 pr-3"></td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.occurs}</td>
                  <td className="py-1.5 pr-3"></td>
                  <td className="py-1.5 pr-3"></td>
                </tr>
              );
            }

            // any (wildcard) row
            if (row.any) {
              return (
                <tr key={row.key} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-1.5 pr-2 text-center text-slate-500" style={{ paddingLeft: padLeft }}>
                    {WILDCARD_GLYPH}
                  </td>
                  <td className="py-1.5 pr-3 font-mono italic text-slate-500">any</td>
                  <td className="py-1.5 pr-3 text-xs text-slate-500">wildcard</td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-slate-500">
                    ns={row.any.namespace ?? "##any"} · {row.any.processContents ?? "strict"}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.occurs}</td>
                  <td className="py-1.5 pr-3"></td>
                  <td className="py-1.5 pr-3"></td>
                </tr>
              );
            }

            // element row
            if (row.element) {
              const e = row.element;
              // A ref particle shows the referenced declaration's type,
              // documentation and default — it declares none itself.
              const decl = resolveElementRef(e, indexById) ?? e;
              const docFull =
                e.annotation?.documentation?.[0]?.text ??
                decl.annotation?.documentation?.[0]?.text ??
                null;
              const docFirst = docFull ? docFull.split(/\r?\n/)[0] : "";
              const typeName = decl.type_name;
              const defOrFix =
                decl.fixed != null ? `[fixed] ${decl.fixed}` : decl.default ?? "—";
              return (
                <tr
                  key={row.key}
                  className="border-b border-slate-100 dark:border-slate-900 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                  onClick={() => setSelected(e.id)}
                >
                  <td className="py-1.5 pr-2" style={{ paddingLeft: padLeft }} />
                  <td className="py-1.5 pr-3 font-mono">{e.name ?? e.ref ?? "?"}</td>
                  <td className="py-1.5 pr-3"><KindBadge kind="element" /></td>
                  <td className="py-1.5 pr-3 font-mono">
                    {typeName ? (
                      <button
                        type="button"
                        className="text-accent hover:underline"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          onTypeClick(typeName);
                        }}
                      >
                        {typeName}
                      </button>
                    ) : decl.type_inline_complex ? (
                      <span className="text-slate-500">(inline complex)</span>
                    ) : decl.type_inline_simple ? (
                      <span className="text-slate-500">(inline simple)</span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.occurs}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs hidden md:table-cell">{defOrFix}</td>
                  <td className="py-1.5 pr-3 text-slate-600 dark:text-slate-400 text-xs max-w-[260px] hidden md:table-cell">
                    <TapToReveal summary={docFirst} details={docFull} />
                  </td>
                </tr>
              );
            }

            return null;
          })}
        </tbody>
      </table>
      </div>
    </section>
  );
}
