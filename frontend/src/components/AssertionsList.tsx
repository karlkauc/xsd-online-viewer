import type { Assertion } from "../types/schema";

interface AssertionsListProps {
  assertions: Assertion[];
}

// Renders XSD 1.1 assertions (xs:assert / xs:assertion). The XPath text is
// shown verbatim — the viewer does not evaluate it. xpathDefaultNamespace
// (when set on the element) is surfaced as a chip so authors can read the
// assertion in the right context.
export function AssertionsList({ assertions }: AssertionsListProps) {
  if (!assertions.length) return null;
  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-2.5 flex items-baseline gap-2">
        <span>Assertions</span>
        <span className="text-[10.5px] font-normal uppercase tracking-wider text-slate-400">
          {assertions.length} · XPath 2.0 · display-only
        </span>
      </h3>
      <div className="space-y-2">
        {assertions.map((a, i) => (
          <AssertionRow key={i} assertion={a} />
        ))}
      </div>
    </section>
  );
}

function AssertionRow({ assertion }: { assertion: Assertion }) {
  const docs = assertion.annotation?.documentation ?? [];
  return (
    <div
      className="rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-amber-500 bg-slate-50 dark:bg-slate-900/60"
      title="XPath as parsed; original whitespace may be normalised by the XML parser"
    >
      <pre className="font-mono text-[12px] px-3 py-2 whitespace-pre-wrap break-all text-slate-800 dark:text-slate-100">
        {assertion.test || <span className="text-slate-400">(empty)</span>}
      </pre>
      {(assertion.xpath_default_namespace || docs.length > 0) && (
        <div className="px-3 pb-2 -mt-1 flex flex-wrap items-center gap-2">
          {assertion.xpath_default_namespace && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-800/60"
              title={`xpathDefaultNamespace: ${assertion.xpath_default_namespace}`}
            >
              ns: {assertion.xpath_default_namespace}
            </span>
          )}
          {docs.map((doc, di) => (
            <span
              key={di}
              className="text-[11.5px] text-slate-600 dark:text-slate-300 italic leading-snug"
            >
              {doc.text}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
