import type { ElementDecl, IdentityConstraint, NodeIndexEntry } from "../types/schema";
import {
  resolveConstraintPaths,
  type PathToken,
  type ResolveContext,
} from "../lib/constraintXPath";
import { SourceLineLink } from "./SourceLineLink";
import { VersionBadge } from "./VersionBadge";
import { resolveReferTarget } from "../lib/constraintRefer";

type SetSelected = (id: string) => void;

interface IdentityConstraintsListProps {
  /** The constraints declared directly on `host` (`ElementDecl.identity_constraints`). */
  constraints: IdentityConstraint[];
  /** The (ref-resolved) element that declares `constraints` — the starting
   *  context every selector/field XPath is resolved relative to. */
  host: ElementDecl;
  index: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
  constraintsById: Map<string, { constraint: IdentityConstraint; hostId: string }>;
  setSelected: SetSelected;
}

// Renders XSD identity constraints (xs:key / xs:keyref / xs:unique) declared
// on an element: one teal card per constraint, with the selector/field XPath
// steps rendered as clickable buttons wherever they resolve to a concrete
// declaration in this schema (see lib/constraintXPath.ts). The XPath text is
// shown verbatim — the viewer never evaluates it against an instance document.
export function IdentityConstraintsList({
  constraints,
  host,
  index,
  indexById,
  constraintsById,
  setSelected,
}: IdentityConstraintsListProps) {
  if (!constraints.length) return null;
  const ctx: ResolveContext = { index, indexById };
  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-2.5 flex items-baseline gap-2">
        <span>Identity constraints</span>
        <span className="text-[10.5px] font-normal uppercase tracking-wider text-slate-400">
          {constraints.length} · xs:key / xs:keyref / xs:unique · display-only
        </span>
      </h3>
      <div className="space-y-3">
        {constraints.map((constraint) => (
          <ConstraintCard
            key={constraint.id}
            constraint={constraint}
            host={host}
            ctx={ctx}
            constraintsById={constraintsById}
            setSelected={setSelected}
          />
        ))}
      </div>
    </section>
  );
}

function ConstraintCard({
  constraint,
  host,
  ctx,
  constraintsById,
  setSelected,
}: {
  constraint: IdentityConstraint;
  host: ElementDecl;
  ctx: ResolveContext;
  constraintsById: Map<string, { constraint: IdentityConstraint; hostId: string }>;
  setSelected: SetSelected;
}) {
  const { selector, fields } = resolveConstraintPaths(constraint, host, ctx);
  const docs = constraint.annotation?.documentation ?? [];
  const referTarget =
    constraint.kind === "keyref" ? resolveReferTarget(constraint, constraintsById) : null;

  return (
    <div
      className="rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-teal-500 bg-slate-50 dark:bg-slate-900/60 px-3 py-2 space-y-1.5"
      title="XPath as parsed; original whitespace may be normalised by the XML parser"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <KindChip kind={constraint.kind} />
        <code className="font-mono text-[12px] text-slate-800 dark:text-slate-100">
          {constraint.name}
        </code>
        {constraint.version_constraints && <VersionBadge vc={constraint.version_constraints} />}
        {constraint.source_ref && (
          <SourceLineLink sourceRef={constraint.source_ref} className="ml-auto" />
        )}
      </div>
      <div className="text-[11.5px] space-y-1">
        <PathRow label="selector">
          <ConstraintPath tokens={selector} setSelected={setSelected} />
        </PathRow>
        {fields.map((tokens, i) => (
          <PathRow key={i} label="field">
            <ConstraintPath tokens={tokens} setSelected={setSelected} />
          </PathRow>
        ))}
        {constraint.kind === "keyref" && (
          <PathRow label="refers to">
            {referTarget ? (
              <button
                type="button"
                className="font-mono text-teal-700 dark:text-teal-300 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
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
          </PathRow>
        )}
      </div>
      {constraint.xpath_default_namespace && (
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border bg-teal-50 text-teal-800 border-teal-200 dark:bg-teal-900/30 dark:text-teal-200 dark:border-teal-800/60"
          title={`xpathDefaultNamespace: ${constraint.xpath_default_namespace}`}
        >
          ns: {constraint.xpath_default_namespace}
        </span>
      )}
      {docs.map((doc, i) => (
        <div
          key={i}
          className="text-[11.5px] text-slate-600 dark:text-slate-300 italic leading-snug"
        >
          {doc.text}
        </div>
      ))}
    </div>
  );
}

function PathRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-slate-400 dark:text-slate-500 shrink-0">{label}</span>
      {children}
    </div>
  );
}

function KindChip({ kind }: { kind: IdentityConstraint["kind"] }) {
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10.5px] font-medium border bg-teal-50 text-teal-800 border-teal-200 dark:bg-teal-900/30 dark:text-teal-200 dark:border-teal-800/60">
      {kind}
    </span>
  );
}

interface ConstraintPathProps {
  tokens: PathToken[];
  setSelected: SetSelected;
}

// Renders one selector/field XPath as its verbatim text, with every step
// that resolved to a concrete declaration (lib/constraintXPath.ts) turned
// into a clickable teal button; unresolved steps and separators stay plain.
// Exported for reuse by ContentModelView/IdentityConstraintsTable.tsx.
export function ConstraintPath({ tokens, setSelected }: ConstraintPathProps) {
  return (
    <span className="font-mono text-[12px] break-all">
      {tokens.map((token, i) => {
        if (token.targetId) {
          return (
            <button
              key={i}
              type="button"
              className="text-teal-700 dark:text-teal-300 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
              title={`Go to ${token.text}`}
              onClick={() => setSelected(token.targetId!)}
            >
              {token.text}
            </button>
          );
        }
        return (
          <span
            key={i}
            className={
              token.kind === "sep"
                ? "text-slate-400 dark:text-slate-500"
                : "text-slate-600 dark:text-slate-300"
            }
          >
            {token.text}
          </span>
        );
      })}
    </span>
  );
}
