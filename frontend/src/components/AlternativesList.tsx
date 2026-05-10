import type { ReactNode } from "react";
import type { Alternative } from "../types/schema";

interface AlternativesListProps {
  alternatives: Alternative[];
  /** Render a clickable type reference. Provided by the parent so this
   *  component does not need direct access to the selection store. */
  renderTypeRef: (typeName: string) => ReactNode;
}

// Renders XSD 1.1 ``xs:alternative`` clauses as an ordered if/else ladder.
// Predicates are shown verbatim — the viewer never evaluates them.
export function AlternativesList({
  alternatives,
  renderTypeRef,
}: AlternativesListProps) {
  if (!alternatives.length) return null;
  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-2.5 flex items-baseline gap-2">
        <span>Type alternatives</span>
        <span className="text-[10.5px] font-normal uppercase tracking-wider text-slate-400">
          {alternatives.length} · display-only
        </span>
      </h3>
      <ol className="space-y-1.5">
        {alternatives.map((alt, i) => (
          <AlternativeRow
            key={i}
            alt={alt}
            isDefault={alt.test === null}
            renderTypeRef={renderTypeRef}
          />
        ))}
      </ol>
    </section>
  );
}

function AlternativeRow({
  alt,
  isDefault,
  renderTypeRef,
}: {
  alt: Alternative;
  isDefault: boolean;
  renderTypeRef: (typeName: string) => ReactNode;
}) {
  return (
    <li
      className="rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-violet-500 bg-slate-50 dark:bg-slate-900/60 px-3 py-2"
      title="XPath as parsed; original whitespace may be normalised by the XML parser"
    >
      <div className="flex items-baseline gap-2 flex-wrap">
        <Keyword>{isDefault ? "else" : "if"}</Keyword>
        {!isDefault && (
          <code className="font-mono text-[12px] flex-1 min-w-[8rem] break-all text-slate-800 dark:text-slate-100">
            {alt.test || <span className="text-slate-400">(empty)</span>}
          </code>
        )}
        <span className="text-slate-400" aria-hidden="true">
          →
        </span>
        <AlternativeType alt={alt} renderTypeRef={renderTypeRef} />
      </div>
      {alt.xpath_default_namespace && !isDefault && (
        <div className="mt-1 ml-[3.25rem]">
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border bg-violet-50 text-violet-800 border-violet-200 dark:bg-violet-900/30 dark:text-violet-200 dark:border-violet-800/60"
            title={`xpathDefaultNamespace: ${alt.xpath_default_namespace}`}
          >
            ns: {alt.xpath_default_namespace}
          </span>
        </div>
      )}
    </li>
  );
}

function AlternativeType({
  alt,
  renderTypeRef,
}: {
  alt: Alternative;
  renderTypeRef: (typeName: string) => ReactNode;
}) {
  if (alt.type_name) return <>{renderTypeRef(alt.type_name)}</>;
  if (alt.type_inline_complex) return <InlineTag>inline complex</InlineTag>;
  if (alt.type_inline_simple) return <InlineTag>inline simple</InlineTag>;
  return <span className="text-slate-400 text-[11.5px]">(no type)</span>;
}

function Keyword({ children }: { children: ReactNode }) {
  return (
    <span className="font-mono text-[10.5px] uppercase tracking-wider font-semibold text-violet-700 dark:text-violet-300 px-1.5 py-0.5 rounded bg-violet-50 dark:bg-violet-900/30 border border-violet-200 dark:border-violet-800/60">
      {children}
    </span>
  );
}

function InlineTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10.5px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
      {children}
    </span>
  );
}
