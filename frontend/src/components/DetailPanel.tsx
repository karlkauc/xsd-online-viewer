import { useMemo } from "react";
import { useSelection } from "../stores/selectionStore";
import { resolveReference } from "../lib/indexSchema";
import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  NodeIndexEntry,
  SchemaNode,
  SchemaNodeKind,
  SimpleType,
} from "../types/schema";
import { KindBadge } from "./TreeView/KindBadge";
import { FacetGroups } from "./FacetGroups";

// Kind-scoped accent colors — mirror KindBadge so the header's left bar and
// in-row dots read as "same thing as the E/A/CT/ST/G/AG badge".
const KIND_BAR: Record<SchemaNodeKind, string> = {
  element: "bg-blue-500",
  attribute: "bg-amber-500",
  complexType: "bg-violet-500",
  simpleType: "bg-emerald-500",
  group: "bg-pink-500",
  attributeGroup: "bg-rose-500",
};

const KIND_RESOLVERS: { kinds: SchemaNodeKind[]; label: string }[] = [
  { kinds: ["complexType", "simpleType"], label: "type" },
];

export function DetailPanel() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
  const index = useSelection((s) => s.index);
  const usagesByTarget = useSelection((s) => s.usagesByTarget);
  const setSelected = useSelection((s) => s.setSelected);
  const setActiveTab = useSelection((s) => s.setActiveTab);

  const entry = selectedId ? indexById.get(selectedId) : undefined;

  const usages = useMemo(() => {
    if (!entry) return [] as NodeIndexEntry[];
    const keys: string[] = [];
    if (entry.qname) keys.push(entry.qname);
    if (entry.qname && entry.qname.startsWith("{")) {
      const local = entry.qname.split("}").pop() ?? "";
      keys.push(local);
    }
    const seen = new Set<string>();
    const hits: NodeIndexEntry[] = [];
    for (const key of keys) {
      for (const hit of usagesByTarget.get(key) ?? []) {
        if (!seen.has(hit.id)) {
          seen.add(hit.id);
          hits.push(hit);
        }
      }
    }
    const label = entry.label;
    if (label) {
      for (const [target, list] of usagesByTarget.entries()) {
        const matchesPrefixed = target.endsWith(":" + label);
        const matchesExpanded = target.endsWith("}" + label);
        const matchesBare = target === label;
        if (matchesPrefixed || matchesExpanded || matchesBare) {
          for (const hit of list) {
            if (!seen.has(hit.id)) {
              seen.add(hit.id);
              hits.push(hit);
            }
          }
        }
      }
    }
    return hits;
  }, [entry, usagesByTarget]);

  if (!entry) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-slate-500 dark:text-slate-400 text-sm p-8 text-center gap-3">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="opacity-40"
          aria-hidden="true"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
          <path d="M9 13h6M9 17h4" />
        </svg>
        <p>Select a node on the left to see its details.</p>
      </div>
    );
  }

  const node = entry.node;
  return (
    <div className="h-full overflow-auto">
      <Header entry={entry} setActiveTab={setActiveTab} />

      <div className="p-4 space-y-6 text-sm">
        {renderSpecifics(node, index, setSelected)}
        {renderAnnotation(node)}
        {usages.length > 0 && (
          <section>
            <SectionHead title="Used by" count={usages.length} />
            <ul className="space-y-0.5">
              {usages.map((u) => (
                <li key={u.id}>
                  <UsageRow entry={u} onClick={() => setSelected(u.id)} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function Header({
  entry,
  setActiveTab,
}: {
  entry: NodeIndexEntry;
  setActiveTab: (tab: "tree" | "diagram" | "text") => void;
}) {
  return (
    <div className="relative border-b border-slate-200 dark:border-slate-800 bg-gradient-to-b from-slate-50/60 to-white dark:from-slate-900/40 dark:to-slate-950">
      <div
        className={`absolute left-0 top-0 bottom-0 w-[3px] ${KIND_BAR[entry.kind]}`}
        aria-hidden="true"
      />
      <div className="px-4 py-3.5">
        <div className="flex items-center gap-2 mb-1.5 min-w-0">
          <KindBadge kind={entry.kind} />
          <h2 className="text-base font-semibold tracking-tight truncate text-slate-900 dark:text-slate-100">
            {entry.label}
          </h2>
        </div>
        {entry.qname && (
          <code className="block text-[11px] font-mono text-slate-500 dark:text-slate-400 break-all leading-snug">
            {entry.qname}
          </code>
        )}
        {entry.source_ref && (
          <button
            type="button"
            onClick={() => setActiveTab("text")}
            className="mt-2.5 group inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-slate-100 hover:bg-slate-200 dark:bg-slate-800/70 dark:hover:bg-slate-700 text-[11px] text-slate-600 dark:text-slate-300 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            title="Open this declaration in the Text tab"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-slate-500"
              aria-hidden="true"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <path d="M14 2v6h6" />
            </svg>
            <code className="font-mono truncate max-w-[180px]">
              {entry.source_ref.file_id}:{entry.source_ref.line}
            </code>
            <span className="text-slate-400 group-hover:text-accent transition-colors">→</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section specifics (element / attribute / complex / simple)
// ---------------------------------------------------------------------------

type SetSelected = (id: string) => void;

function renderSpecifics(node: SchemaNode, index: NodeIndexEntry[], setSelected: SetSelected) {
  if ("type_inline_complex" in node) return renderElement(node, index, setSelected);
  if ("use" in node) return renderAttribute(node, index, setSelected);
  if ("content_kind" in node) return renderComplexType(node, index, setSelected);
  if ("facets" in node) return renderSimpleType(node, index, setSelected);
  return null;
}

function renderElement(element: ElementDecl, index: NodeIndexEntry[], setSelected: SetSelected) {
  const inlineSimple = element.type_inline_simple ?? null;

  const simpleEntry = !inlineSimple && element.type_name
    ? resolveReference(element.type_name, index, ["simpleType"])
    : undefined;
  const namedSimple = simpleEntry && "facets" in simpleEntry.node
    ? (simpleEntry.node as SimpleType)
    : undefined;

  const complexEntry = !inlineSimple && !namedSimple && element.type_name
    ? resolveReference(element.type_name, index, ["complexType"])
    : undefined;
  const namedComplex = complexEntry && "content_kind" in complexEntry.node
    ? (complexEntry.node as ComplexType)
    : undefined;

  return (
    <section>
      <SectionHead title="Element" />
      <div className="space-y-3">
        <DataRow label="Type">
          {element.type_name ? (
            <TypeRef typeName={element.type_name} index={index} setSelected={setSelected} />
          ) : element.type_inline_complex ? (
            <InlineTag>inline complex</InlineTag>
          ) : (
            <InlineTag>inline simple</InlineTag>
          )}
        </DataRow>
        <DataRow label="Cardinality">
          <Cardinality min={element.min_occurs} max={element.max_occurs} />
        </DataRow>
        {(element.default || element.fixed) && (
          <>
            {element.default && (
              <DataRow label="Default">
                <code className="font-mono text-[12px]">{element.default}</code>
              </DataRow>
            )}
            {element.fixed && (
              <DataRow label="Fixed">
                <code className="font-mono text-[12px]">{element.fixed}</code>
              </DataRow>
            )}
          </>
        )}
        {(element.nillable || element.abstract) && (
          <DataRow label="Flags">
            <div className="flex flex-wrap gap-1">
              {element.nillable && <FlagChip tone="sky">nillable</FlagChip>}
              {element.abstract && <FlagChip tone="violet">abstract</FlagChip>}
            </div>
          </DataRow>
        )}
        {element.substitution_group && (
          <DataRow label="Substitution group">
            <TypeRef
              typeName={element.substitution_group}
              index={index}
              setSelected={setSelected}
            />
          </DataRow>
        )}
      </div>

      {inlineSimple && inlineSimple.facets.length > 0 && (
        <FacetGroups facets={inlineSimple.facets} restriction={inlineSimple} />
      )}
      {namedSimple && namedSimple.facets.length > 0 && (
        <FacetGroups
          facets={namedSimple.facets}
          restriction={namedSimple}
          inheritedFrom={simpleEntry!.label}
        />
      )}
      {namedComplex && namedComplex.simple_content_facets.length > 0 && (
        <FacetGroups
          facets={namedComplex.simple_content_facets}
          restriction={null}
          inheritedFrom={complexEntry!.label}
        />
      )}
    </section>
  );
}

function renderAttribute(
  attr: AttributeDecl,
  index: NodeIndexEntry[],
  setSelected: SetSelected,
) {
  const inheritedEntry = attr.type_name
    ? resolveReference(attr.type_name, index, ["simpleType"])
    : undefined;
  const inheritedSimple =
    inheritedEntry && "facets" in inheritedEntry.node
      ? (inheritedEntry.node as SimpleType)
      : undefined;
  return (
    <section>
      <SectionHead title="Attribute" />
      <div className="space-y-3">
        <DataRow label="Type">
          {attr.type_name ? (
            <TypeRef typeName={attr.type_name} index={index} setSelected={setSelected} />
          ) : attr.type_inline ? (
            <InlineTag>inline simple</InlineTag>
          ) : (
            <Muted>—</Muted>
          )}
        </DataRow>
        <DataRow label="Use">
          <UseChip use={attr.use} />
        </DataRow>
        {attr.default && (
          <DataRow label="Default">
            <code className="font-mono text-[12px]">{attr.default}</code>
          </DataRow>
        )}
        {attr.fixed && (
          <DataRow label="Fixed">
            <code className="font-mono text-[12px]">{attr.fixed}</code>
          </DataRow>
        )}
        {attr.form && (
          <DataRow label="Form">
            <code className="font-mono text-[12px]">{attr.form}</code>
          </DataRow>
        )}
      </div>
      {attr.type_inline && (
        <FacetGroups facets={attr.type_inline.facets} restriction={attr.type_inline} />
      )}
      {inheritedSimple && inheritedSimple.facets.length > 0 && (
        <FacetGroups
          facets={inheritedSimple.facets}
          restriction={inheritedSimple}
          inheritedFrom={inheritedEntry!.label}
        />
      )}
    </section>
  );
}

function renderComplexType(
  complex: ComplexType,
  index: NodeIndexEntry[],
  setSelected: SetSelected,
) {
  return (
    <section>
      <SectionHead title="Complex type" />
      <div className="space-y-3">
        <DataRow label="Content">
          <code className="font-mono text-[12px]">{complex.content_kind}</code>
        </DataRow>
        <DataRow label="Derivation">
          <code className="font-mono text-[12px]">{complex.derivation}</code>
        </DataRow>
        {complex.base && (
          <DataRow label="Base">
            <TypeRef typeName={complex.base} index={index} setSelected={setSelected} />
          </DataRow>
        )}
        {(complex.abstract || complex.mixed) && (
          <DataRow label="Flags">
            <div className="flex flex-wrap gap-1">
              {complex.abstract && <FlagChip tone="violet">abstract</FlagChip>}
              {complex.mixed && <FlagChip tone="sky">mixed</FlagChip>}
            </div>
          </DataRow>
        )}
      </div>
      {complex.simple_content_facets.length > 0 && (
        <FacetGroups facets={complex.simple_content_facets} restriction={null} />
      )}
      {complex.attributes.length > 0 && (
        <div className="mt-4">
          <SubHead>Attributes ({complex.attributes.length})</SubHead>
          <ul className="space-y-0.5 mt-1">
            {complex.attributes.map((a) => (
              <li
                key={a.id}
                className="font-mono text-[12px] px-2 py-1 rounded hover:bg-slate-50 dark:hover:bg-slate-900/60 transition-colors"
              >
                <span className="text-amber-600 dark:text-amber-400">@{a.name}</span>
                <span className="text-slate-400 ml-1.5">
                  {a.type_name ?? "inline"} · {a.use}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {complex.attribute_group_refs.length > 0 && (
        <div className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          <span className="uppercase tracking-wide text-[10px] font-semibold">
            Attribute groups
          </span>
          <div className="mt-1 font-mono">{complex.attribute_group_refs.join(", ")}</div>
        </div>
      )}
    </section>
  );
}

function renderSimpleType(
  simple: SimpleType,
  index: NodeIndexEntry[],
  setSelected: SetSelected,
) {
  return (
    <section>
      <SectionHead title="Simple type" />
      <div className="space-y-3">
        <DataRow label="Derivation">
          <code className="font-mono text-[12px]">{simple.derivation}</code>
        </DataRow>
        {simple.base && (
          <DataRow label="Base">
            <TypeRef typeName={simple.base} index={index} setSelected={setSelected} />
          </DataRow>
        )}
        {simple.item_type && (
          <DataRow label="Item type">
            <TypeRef typeName={simple.item_type} index={index} setSelected={setSelected} />
          </DataRow>
        )}
        {simple.member_types.length > 0 && (
          <DataRow label="Members">
            <div className="flex flex-wrap gap-1">
              {simple.member_types.map((m) => (
                <TypeRef key={m} typeName={m} index={index} setSelected={setSelected} />
              ))}
            </div>
          </DataRow>
        )}
      </div>
      <FacetGroups facets={simple.facets} restriction={null} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Annotation: documentation / comments / appinfo
// ---------------------------------------------------------------------------

function renderAnnotation(node: SchemaNode) {
  const annotation = "annotation" in node ? node.annotation : null;
  if (!annotation) return null;
  const { documentation, appinfo, comments } = annotation;
  if (!documentation.length && !appinfo.length && !comments.length) return null;
  return (
    <section>
      <SectionHead title="Documentation" />
      <div className="space-y-3">
        {documentation.map((doc, i) => (
          <div
            key={`doc-${i}`}
            className="border-l-2 border-slate-200 dark:border-slate-800 pl-3 py-0.5"
          >
            {doc.lang && (
              <span className="inline-block mb-1 text-[10px] uppercase tracking-wide font-semibold text-slate-400">
                {doc.lang}
              </span>
            )}
            <p className="text-[13px] leading-relaxed whitespace-pre-wrap text-slate-700 dark:text-slate-200">
              {doc.text}
            </p>
          </div>
        ))}
        {comments.length > 0 && (
          <div className="space-y-1">
            {comments.map((c, i) => (
              <p
                key={`c-${i}`}
                className="font-mono text-[11px] italic text-slate-500 dark:text-slate-400 pl-3 border-l border-dashed border-slate-300 dark:border-slate-700"
              >
                {c.trim()}
              </p>
            ))}
          </div>
        )}
        {appinfo.map((a, i) => (
          <div key={`ai-${i}`}>
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-[10px] uppercase tracking-wide font-semibold text-amber-700 dark:text-amber-400">
                appinfo
              </span>
              {a.source_uri && (
                <code className="text-[10px] font-mono text-slate-500 dark:text-slate-400 truncate">
                  {a.source_uri}
                </code>
              )}
            </div>
            <pre className="p-2.5 rounded-md bg-amber-50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/40 text-[11px] font-mono overflow-auto text-amber-900 dark:text-amber-100">
              {a.raw_xml}
            </pre>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

function SectionHead({ title, count }: { title: string; count?: number }) {
  return (
    <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2.5 flex items-center gap-1.5">
      {title}
      {typeof count === "number" && (
        <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[10px] font-medium normal-case tracking-normal">
          {count}
        </span>
      )}
    </h3>
  );
}

function SubHead({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
      {children}
    </h4>
  );
}

function DataRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,7.5rem)_1fr] gap-x-3 items-baseline">
      <dt className="text-[11px] font-medium text-slate-500 dark:text-slate-400 pt-0.5">
        {label}
      </dt>
      <dd className="min-w-0 break-all">{children}</dd>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-slate-400 dark:text-slate-600">{children}</span>;
}

function InlineTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10.5px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
      {children}
    </span>
  );
}

function Cardinality({
  min,
  max,
}: {
  min: number;
  max: number | "unbounded";
}) {
  const maxStr = max === "unbounded" ? "∞" : String(max);
  let descriptor: string | null = null;
  if (min === 0 && max === 1) descriptor = "optional";
  else if (min === 1 && max === 1) descriptor = "required";
  else if (min === 0 && max === "unbounded") descriptor = "any";
  else if (min === 1 && max === "unbounded") descriptor = "one or more";
  else if (max === "unbounded") descriptor = `≥ ${min}`;
  else if (String(min) === maxStr) descriptor = `exactly ${min}`;
  const tone =
    min === 0
      ? "text-slate-500 dark:text-slate-400"
      : "text-amber-700 dark:text-amber-400";
  return (
    <div className="inline-flex items-center gap-2">
      <span className="inline-flex items-center font-mono text-[11.5px] px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900">
        [{min}..{maxStr}]
      </span>
      {descriptor && (
        <span className={`text-[11px] ${tone}`}>{descriptor}</span>
      )}
    </div>
  );
}

type FlagTone = "sky" | "violet" | "emerald";
const FLAG_TONE: Record<FlagTone, string> = {
  sky: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-300 dark:border-sky-800/60",
  violet:
    "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-800/60",
  emerald:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800/60",
};

function FlagChip({ tone, children }: { tone: FlagTone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10.5px] font-medium border ${FLAG_TONE[tone]}`}
    >
      <span className="w-1 h-1 rounded-full bg-current" aria-hidden="true" />
      {children}
    </span>
  );
}

function UseChip({ use }: { use: string }) {
  const tone: FlagTone = use === "required" ? "violet" : use === "prohibited" ? "emerald" : "sky";
  return <FlagChip tone={tone}>{use}</FlagChip>;
}

// Renders a type reference. If the type resolves to an indexed simple/complex
// type, it becomes a clickable chip with a kind-colored dot.
function TypeRef({
  typeName,
  index,
  setSelected,
}: {
  typeName: string;
  index: NodeIndexEntry[];
  setSelected: SetSelected;
}) {
  const target = resolveTypeRef(typeName, index);
  if (!target) {
    return <code className="font-mono text-[12px] text-slate-700 dark:text-slate-200">{typeName}</code>;
  }
  return (
    <button
      type="button"
      onClick={() => setSelected(target.id)}
      className="group inline-flex items-center gap-1.5 font-mono text-[12px] px-1.5 py-0.5 -mx-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors text-slate-800 dark:text-slate-100"
      title={`Go to ${target.kind} ${target.label}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${KIND_BAR[target.kind]}`}
        aria-hidden="true"
      />
      <span className="truncate">{typeName}</span>
      <span className="text-slate-300 dark:text-slate-600 group-hover:text-accent transition-colors">
        →
      </span>
    </button>
  );
}

function resolveTypeRef(typeName: string, index: NodeIndexEntry[]) {
  for (const { kinds } of KIND_RESOLVERS) {
    const hit = resolveReference(typeName, index, kinds);
    if (hit) return hit;
  }
  return undefined;
}

// Used-by row
function UsageRow({ entry, onClick }: { entry: NodeIndexEntry; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left group hover:bg-slate-100 dark:hover:bg-slate-800/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors"
    >
      <KindBadge kind={entry.kind} />
      <span className="font-mono text-[12.5px] truncate flex-1 text-slate-800 dark:text-slate-100">
        {entry.label}
      </span>
      <span
        className="text-slate-300 dark:text-slate-600 group-hover:text-accent group-hover:translate-x-0.5 transition-all"
        aria-hidden="true"
      >
        →
      </span>
    </button>
  );
}

// Re-export for downstream callers (tests, future imports)
export { FacetGroups } from "./FacetGroups";
