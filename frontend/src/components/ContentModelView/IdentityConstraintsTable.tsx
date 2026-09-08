import type { ElementDecl, IdentityConstraint, NodeIndexEntry } from "../../types/schema";
import { resolveConstraintPaths, type ResolveContext } from "../../lib/constraintXPath";
import { ConstraintPath } from "../IdentityConstraintsList";
import { resolveReferTarget } from "../../lib/constraintRefer";
import { SourceLineLink } from "../SourceLineLink";
import { useSelection } from "../../stores/selectionStore";

interface IdentityConstraintsTableProps {
  /** The constraints declared directly on `host` (`ElementDecl.identity_constraints`). */
  constraints: IdentityConstraint[];
  /** The (ref-resolved) element that declares `constraints`. */
  host: ElementDecl;
  index: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
  constraintsById: Map<string, { constraint: IdentityConstraint; hostId: string }>;
}

// Centre-pane table for the identity constraints (xs:key / xs:keyref /
// xs:unique) declared on the selected element. Mirrors AttributesTable's/
// AssertionsTable's layout; selector/field steps reuse ConstraintPath so
// resolved steps stay clickable here too.
export function IdentityConstraintsTable({
  constraints,
  host,
  index,
  indexById,
  constraintsById,
}: IdentityConstraintsTableProps) {
  const setSelected = useSelection((s) => s.setSelected);
  if (!constraints.length) return null;
  const ctx: ResolveContext = { index, indexById };

  return (
    <section className="px-4 md:px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        Identity constraints
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[20rem] md:min-w-0 text-sm border-collapse">
          <thead>
            <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
              <th className="py-1.5 pr-3 font-semibold">Kind</th>
              <th className="py-1.5 pr-3 font-semibold">Name</th>
              <th className="py-1.5 pr-3 font-semibold">Selector</th>
              <th className="py-1.5 pr-3 font-semibold">Field(s)</th>
              <th className="py-1.5 pr-3 font-semibold">Refers to</th>
              <th className="py-1.5 pr-3 font-semibold hidden md:table-cell">Line</th>
            </tr>
          </thead>
          <tbody>
            {constraints.map((constraint) => {
              const { selector, fields } = resolveConstraintPaths(constraint, host, ctx);
              const referTarget =
                constraint.kind === "keyref"
                  ? resolveReferTarget(constraint, constraintsById)
                  : null;
              return (
                <tr
                  key={constraint.id}
                  className="border-b border-slate-100 dark:border-slate-900"
                >
                  <td className="py-1.5 pr-3 font-mono text-teal-700 dark:text-teal-300">
                    {constraint.kind}
                  </td>
                  <td className="py-1.5 pr-3 font-mono">{constraint.name}</td>
                  <td className="py-1.5 pr-3">
                    <ConstraintPath tokens={selector} setSelected={setSelected} />
                  </td>
                  <td className="py-1.5 pr-3">
                    {fields.map((tokens, i) => (
                      <div key={i}>
                        <ConstraintPath tokens={tokens} setSelected={setSelected} />
                      </div>
                    ))}
                  </td>
                  <td className="py-1.5 pr-3">
                    {constraint.kind !== "keyref" ? (
                      <span className="text-slate-400">—</span>
                    ) : referTarget ? (
                      <button
                        type="button"
                        className="font-mono text-teal-700 dark:text-teal-300 hover:underline"
                        title={`Go to ${referTarget.name}`}
                        onClick={() => setSelected(referTarget.hostId)}
                      >
                        ⚿ {referTarget.name} →
                      </button>
                    ) : (
                      <code
                        className="font-mono text-slate-500 dark:text-slate-400"
                        title="key not found in this schema"
                      >
                        {constraint.refer ?? "?"}
                      </code>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 hidden md:table-cell">
                    {constraint.source_ref ? (
                      <SourceLineLink sourceRef={constraint.source_ref} />
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
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
