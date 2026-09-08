import type { AssertionGroup } from "../lib/assertions";
import { countAssertions } from "../lib/assertions";
import type { Assertion } from "../types/schema";
import { SourceLineLink } from "./SourceLineLink";
import { VersionBadge } from "./VersionBadge";

interface AssertionsListProps {
  /** Legacy prop: a flat list of assertions, wrapped into a single group with
   *  no "from" label. Kept for callers that don't need base-chain grouping. */
  assertions?: Assertion[];
  /** Assertions grouped by the type that declares them — the type's own
   *  assertions plus any contributed by its extension/restriction base
   *  chain (see lib/assertions.ts). Takes precedence over `assertions`. */
  groups?: AssertionGroup[];
}

// Renders XSD 1.1 assertions (xs:assert / xs:assertion) contributed by a
// declaration's type, including any it inherited from a base type. The
// XPath text is shown verbatim — the viewer does not evaluate it.
// xpathDefaultNamespace (when set on the element) is surfaced as a chip so
// authors can read the assertion in the right context.
export function AssertionsList({ assertions, groups }: AssertionsListProps) {
  const resolvedGroups: AssertionGroup[] =
    groups ?? (assertions ? [{ assertions, from: null, typeId: "" }] : []);
  const total = countAssertions(resolvedGroups);
  if (!total) return null;
  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-2.5 flex items-baseline gap-2">
        <span>Assertions</span>
        <span className="text-[10.5px] font-normal uppercase tracking-wider text-slate-400">
          {total} · XPath 2.0 · display-only
        </span>
      </h3>
      <div className="space-y-3">
        {resolvedGroups.map((group, gi) => (
          <div key={group.typeId || gi}>
            {group.from && (
              <div className="text-[11px] font-normal text-slate-400 mb-1">
                from <code className="font-mono">{group.from}</code>
              </div>
            )}
            <div className="space-y-2">
              {group.assertions.map((a, i) => (
                <AssertionRow key={i} assertion={a} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AssertionRow({ assertion }: { assertion: Assertion }) {
  const docs = assertion.annotation?.documentation ?? [];
  const hasFooter =
    assertion.xpath_default_namespace ||
    docs.length > 0 ||
    assertion.version_constraints ||
    assertion.source_ref;
  return (
    <div
      className="rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-amber-500 bg-slate-50 dark:bg-slate-900/60"
      title="XPath as parsed; original whitespace may be normalised by the XML parser"
    >
      <pre className="font-mono text-[12px] px-3 py-2 whitespace-pre-wrap break-all text-slate-800 dark:text-slate-100">
        {assertion.test || <span className="text-slate-400">(empty)</span>}
      </pre>
      {hasFooter && (
        <div className="px-3 pb-2 -mt-1 flex flex-wrap items-center gap-2">
          {assertion.xpath_default_namespace && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-800/60"
              title={`xpathDefaultNamespace: ${assertion.xpath_default_namespace}`}
            >
              ns: {assertion.xpath_default_namespace}
            </span>
          )}
          {assertion.version_constraints && (
            <VersionBadge vc={assertion.version_constraints} />
          )}
          {docs.map((doc, di) => (
            <span
              key={di}
              className="text-[11.5px] text-slate-600 dark:text-slate-300 italic leading-snug"
            >
              {doc.text}
            </span>
          ))}
          {assertion.source_ref && (
            <SourceLineLink sourceRef={assertion.source_ref} className="ml-auto" />
          )}
        </div>
      )}
    </div>
  );
}
