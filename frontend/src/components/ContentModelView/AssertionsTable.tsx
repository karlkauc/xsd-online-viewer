import type { AssertionGroup } from "../../lib/assertions";
import { SourceLineLink } from "../SourceLineLink";
import { VersionBadge } from "../VersionBadge";

interface AssertionsTableProps {
  /** Assertions grouped by the type that declares them (own type + any
   *  extension/restriction base chain) — see lib/assertions.ts. */
  groups: AssertionGroup[];
}

// Centre-pane table for the assertions (xs:assert / xs:assertion) contributed
// by the selected declaration's type, including any inherited from a base
// type via an extension/restriction chain.
export function AssertionsTable({ groups }: AssertionsTableProps) {
  const rows = groups.flatMap((group, gi) =>
    group.assertions.map((assertion, ai) => ({
      assertion,
      from: group.from,
      key: `${group.typeId || gi}-${ai}`,
    })),
  );
  if (!rows.length) return null;

  return (
    <section className="px-4 md:px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        Assertions
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[20rem] md:min-w-0 text-sm border-collapse">
          <thead>
            <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
              <th className="py-1.5 pr-3 font-semibold">⚖</th>
              <th className="py-1.5 pr-3 font-semibold">Test</th>
              <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">ns</th>
              <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">Line</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ assertion, from, key }) => (
              <tr
                key={key}
                className="border-b border-slate-100 dark:border-slate-900"
              >
                <td className="py-1.5 pr-3 font-mono text-amber-600 dark:text-amber-400">⚖</td>
                <td className="py-1.5 pr-3 font-mono break-all">
                  {assertion.test || <span className="text-slate-400">(empty)</span>}
                  {from && (
                    <span className="ml-1.5 text-[10px] font-sans text-slate-400">
                      from {from}
                    </span>
                  )}
                  {assertion.version_constraints && (
                    <span className="ml-1.5 inline-block align-middle">
                      <VersionBadge vc={assertion.version_constraints} />
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-3 font-mono hidden md:table-cell">
                  {assertion.xpath_default_namespace ?? "—"}
                </td>
                <td className="py-1.5 pr-3 hidden md:table-cell">
                  {assertion.source_ref ? (
                    <SourceLineLink sourceRef={assertion.source_ref} />
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
