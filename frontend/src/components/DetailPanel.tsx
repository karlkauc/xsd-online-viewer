import { Fragment, useMemo } from "react";
import { useSelection } from "../stores/selectionStore";
import { resolveReference } from "../lib/indexSchema";
import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  Facet,
  FacetKind,
  NodeIndexEntry,
  SchemaNode,
  SimpleType,
} from "../types/schema";
import { KindBadge } from "./TreeView/KindBadge";

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
    // Match both "tns:Foo" and "{uri}Foo" conventions used in referrers.
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
    // Catch prefix-variant references (tns:Foo, ex:Foo, bare Foo) by
    // matching the local name against every stored reference target.
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
      <div className="h-full flex items-center justify-center text-slate-500 dark:text-slate-400 text-sm p-8 text-center">
        Select a node on the left to see its details.
      </div>
    );
  }

  const node = entry.node;
  return (
    <div className="h-full overflow-auto">
      <div className="p-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <KindBadge kind={entry.kind} />
          <h2 className="font-mono text-lg">{entry.label}</h2>
        </div>
        {entry.qname && (
          <p className="text-xs font-mono text-slate-500 dark:text-slate-400 mt-1 break-all">
            {entry.qname}
          </p>
        )}
        {entry.source_ref && (
          <div className="flex items-center gap-2 mt-1">
            <p className="text-xs text-slate-400">
              Source: file <code>{entry.source_ref.file_id}</code>, line{" "}
              {entry.source_ref.line}
            </p>
            <button
              type="button"
              className="text-xs text-accent hover:underline"
              onClick={() => setActiveTab("text")}
            >
              View in source →
            </button>
          </div>
        )}
      </div>

      <div className="p-4 space-y-5 text-sm">
        {renderSpecifics(node, index)}
        {renderAnnotation(node)}
        {usages.length > 0 && (
          <section>
            <h3 className="font-semibold mb-2">Used by ({usages.length})</h3>
            <ul className="space-y-1">
              {usages.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(u.id)}
                    className="font-mono text-accent hover:underline"
                  >
                    <KindBadge kind={u.kind} /> {u.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function renderSpecifics(node: SchemaNode, index: NodeIndexEntry[]) {
  if ("type_inline_complex" in node) return renderElement(node, index);
  if ("use" in node) return renderAttribute(node, index);
  if ("content_kind" in node) return renderComplexType(node);
  if ("facets" in node) return renderSimpleType(node);
  return null;
}

function renderElement(element: ElementDecl, index: NodeIndexEntry[]) {
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
      <h3 className="font-semibold mb-2">Element</h3>
      <KeyValue
        rows={[
          ["Type", element.type_name ?? (element.type_inline_complex ? "(inline complex)" : "(inline simple)")],
          ["Min occurs", String(element.min_occurs)],
          ["Max occurs", String(element.max_occurs)],
          ["Default", element.default ?? "—"],
          ["Fixed", element.fixed ?? "—"],
          ["Nillable", String(element.nillable)],
          ["Abstract", String(element.abstract)],
          ["Substitution group", element.substitution_group ?? "—"],
        ]}
      />
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

function renderAttribute(attr: AttributeDecl, index: NodeIndexEntry[]) {
  const inheritedEntry = attr.type_name
    ? resolveReference(attr.type_name, index, ["simpleType"])
    : undefined;
  const inheritedSimple =
    inheritedEntry && "facets" in inheritedEntry.node
      ? (inheritedEntry.node as SimpleType)
      : undefined;
  return (
    <section>
      <h3 className="font-semibold mb-2">Attribute</h3>
      <KeyValue
        rows={[
          ["Type", attr.type_name ?? (attr.type_inline ? "(inline simple)" : "—")],
          ["Use", attr.use],
          ["Default", attr.default ?? "—"],
          ["Fixed", attr.fixed ?? "—"],
          ["Form", attr.form ?? "—"],
        ]}
      />
      {attr.type_inline && (
        <FacetGroups
          facets={attr.type_inline.facets}
          restriction={attr.type_inline}
        />
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

function renderComplexType(complex: ComplexType) {
  return (
    <section>
      <h3 className="font-semibold mb-2">Complex type</h3>
      <KeyValue
        rows={[
          ["Content", complex.content_kind],
          ["Derivation", complex.derivation],
          ["Base", complex.base ?? "—"],
          ["Abstract", String(complex.abstract)],
          ["Mixed", String(complex.mixed)],
        ]}
      />
      {complex.simple_content_facets.length > 0 && (
        <FacetGroups facets={complex.simple_content_facets} restriction={null} />
      )}
      {complex.attributes.length > 0 && (
        <div className="mt-3">
          <h4 className="font-semibold mb-1">Attributes</h4>
          <ul className="list-disc ml-5">
            {complex.attributes.map((a) => (
              <li key={a.id} className="font-mono">
                @{a.name} <span className="text-slate-500">({a.type_name ?? "inline"}, {a.use})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {complex.attribute_group_refs.length > 0 && (
        <p className="mt-2 text-slate-500">
          Attribute groups: <span className="font-mono">{complex.attribute_group_refs.join(", ")}</span>
        </p>
      )}
    </section>
  );
}

function renderSimpleType(simple: SimpleType) {
  return (
    <section>
      <h3 className="font-semibold mb-2">Simple type</h3>
      <KeyValue
        rows={[
          ["Derivation", simple.derivation],
          ["Base", simple.base ?? "—"],
          ["Item type", simple.item_type ?? "—"],
          ["Members", simple.member_types.join(" ") || "—"],
        ]}
      />
      <FacetGroups facets={simple.facets} restriction={null} />
    </section>
  );
}

function renderAnnotation(node: SchemaNode) {
  const annotation = "annotation" in node ? node.annotation : null;
  if (!annotation) return null;
  const { documentation, appinfo, comments } = annotation;
  if (!documentation.length && !appinfo.length && !comments.length) return null;
  return (
    <section>
      <h3 className="font-semibold mb-2">Documentation</h3>
      {documentation.map((doc, i) => (
        <p key={`doc-${i}`} className="mb-1 whitespace-pre-wrap">
          {doc.lang && <span className="text-xs text-slate-500 mr-2">[{doc.lang}]</span>}
          {doc.text}
        </p>
      ))}
      {comments.map((c, i) => (
        <p key={`c-${i}`} className="mb-1 italic text-slate-600 dark:text-slate-400">
          // {c.trim()}
        </p>
      ))}
      {appinfo.map((a, i) => (
        <pre
          key={`ai-${i}`}
          className="mt-2 p-2 rounded bg-amber-50 dark:bg-amber-950/20 text-xs overflow-auto"
        >
          {a.source_uri ? `source=${a.source_uri}\n` : ""}
          {a.raw_xml}
        </pre>
      ))}
    </section>
  );
}

function KeyValue({ rows }: { rows: [string, string | null | undefined][] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k} className="border-b border-slate-100 dark:border-slate-800 last:border-0">
            <th className="text-left font-medium text-slate-500 py-1 pr-3 w-1/3">{k}</th>
            <td className="font-mono py-1 break-all">{v ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ============================================================================
// FacetGroups — structured rendering of <xs:restriction>/<xs:list> facets.
// ============================================================================

type GroupId =
  | "restriction"
  | "enumeration"
  | "range"
  | "precision"
  | "length"
  | "pattern"
  | "whitespace"
  | "other";

const FACET_GROUP: Partial<Record<FacetKind, GroupId>> = {
  enumeration: "enumeration",
  minInclusive: "range",
  maxInclusive: "range",
  minExclusive: "range",
  maxExclusive: "range",
  totalDigits: "precision",
  fractionDigits: "precision",
  length: "length",
  minLength: "length",
  maxLength: "length",
  pattern: "pattern",
  whiteSpace: "whitespace",
};

interface FacetGroupsProps {
  facets: Facet[];
  /** Optional: include the restriction block when we have an owning SimpleType.
   *  Pass null from call sites where base/derivation is already shown above. */
  restriction?:
    | Pick<SimpleType, "base" | "derivation" | "item_type" | "member_types">
    | null;
  /** Section-title suffix for inherited facets (e.g. attribute → named simple). */
  inheritedFrom?: string | null;
}

export function FacetGroups({ facets, restriction, inheritedFrom }: FacetGroupsProps) {
  if (!facets.length && !restriction) return null;

  const byGroup = new Map<GroupId, Facet[]>();
  for (const f of facets) {
    const g = FACET_GROUP[f.kind] ?? "other";
    const arr = byGroup.get(g) ?? [];
    arr.push(f);
    byGroup.set(g, arr);
  }

  const order: GroupId[] = [
    "restriction",
    "enumeration",
    "range",
    "precision",
    "length",
    "pattern",
    "whitespace",
    "other",
  ];

  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-3 flex items-baseline gap-2">
        <span>Facets &amp; Restrictions</span>
        {inheritedFrom && (
          <span className="text-xs font-normal text-slate-400">
            · inherited from <code>{inheritedFrom}</code>
          </span>
        )}
      </h3>
      <div className="space-y-4">
        {order.map((gid) => {
          if (gid === "restriction") {
            return restriction ? (
              <RestrictionGroup key={gid} restriction={restriction} />
            ) : null;
          }
          const list = byGroup.get(gid);
          if (!list || !list.length) return null;
          switch (gid) {
            case "enumeration":
              return <EnumerationGroup key={gid} facets={list} />;
            case "range":
              return (
                <RangeGroup
                  key={gid}
                  facets={list}
                  digits={byGroup.get("precision") ?? []}
                />
              );
            case "precision":
              return byGroup.has("range") ? null : (
                <PrecisionGroup key={gid} facets={list} />
              );
            case "length":
              return <LengthGroup key={gid} facets={list} />;
            case "pattern":
              return <PatternGroup key={gid} facets={list} />;
            case "whitespace":
              return <WhitespaceGroup key={gid} facets={list} />;
            case "other":
              return <OtherGroup key={gid} facets={list} />;
            default:
              return null;
          }
        })}
      </div>
    </section>
  );
}

function GroupHead({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="text-[10.5px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1.5">
      {title}
      {meta && <span className="font-normal text-slate-400 ml-1">· {meta}</span>}
    </div>
  );
}

function RestrictionGroup({
  restriction: r,
}: {
  restriction: NonNullable<FacetGroupsProps["restriction"]>;
}) {
  const rows: [string, string][] = [];
  if (r.base) rows.push(["Base", r.base]);
  if (r.derivation) rows.push(["Derivation", r.derivation]);
  if (r.item_type) rows.push(["Item type", r.item_type]);
  if (r.member_types.length) rows.push(["Members", r.member_types.join(" ")]);
  if (!rows.length) return null;
  return (
    <div>
      <GroupHead title="Restriction" />
      <table className="w-full text-xs">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <th className="text-left font-normal text-slate-500 py-0.5 pr-3 w-1/3">{k}</th>
              <td className="font-mono py-0.5 break-all">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EnumerationGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Enumeration" meta={`${facets.length} values`} />
      <div className="flex flex-wrap gap-1">
        {facets.map((f, i) => (
          <span
            key={i}
            className="font-mono text-[11px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:border-emerald-800/50"
            title={f.fixed ? "fixed" : undefined}
          >
            {f.value}
          </span>
        ))}
      </div>
    </div>
  );
}

function RangeGroup({ facets, digits }: { facets: Facet[]; digits: Facet[] }) {
  const find = (k: FacetKind) => facets.find((f) => f.kind === k)?.value;
  const minI = find("minInclusive");
  const minE = find("minExclusive");
  const maxI = find("maxInclusive");
  const maxE = find("maxExclusive");
  const minVal = minI ?? minE ?? "−∞";
  const maxVal = maxI ?? maxE ?? "+∞";
  const minOp = minI ? "≥" : minE ? ">" : "";
  const maxOp = maxI ? "≤" : maxE ? "<" : "";
  return (
    <div>
      <GroupHead title="Range" />
      <div className="flex items-center gap-2 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3 py-1.5 font-mono text-xs">
        <span className="text-slate-400 text-[10px]">{minOp}</span>
        <span className="font-semibold text-emerald-700 dark:text-emerald-300">{minVal}</span>
        <span className="flex-1 h-[3px] rounded bg-gradient-to-r from-slate-300 via-slate-500 to-slate-300 dark:from-slate-700 dark:via-slate-500 dark:to-slate-700" />
        <span className="font-semibold text-emerald-700 dark:text-emerald-300">{maxVal}</span>
        <span className="text-slate-400 text-[10px]">{maxOp}</span>
      </div>
      {digits.length > 0 && (
        <div className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
          {digits.map((d) => (
            <Fragment key={d.kind}>
              <span className="text-slate-500">{d.kind}</span>
              <span>{d.value}</span>
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}

function PrecisionGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Precision" />
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
        {facets.map((f) => (
          <Fragment key={f.kind}>
            <span className="text-slate-500">{f.kind}</span>
            <span>{f.value}</span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function LengthGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Length" />
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
        {facets.map((f) => (
          <Fragment key={f.kind}>
            <span className="text-slate-500">{f.kind}</span>
            <span>{f.value} chars</span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function PatternGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead
        title="Pattern"
        meta={facets.length > 1 ? `${facets.length} alternatives` : undefined}
      />
      <div className="space-y-1">
        {facets.map((f, i) => (
          <div
            key={i}
            className="font-mono text-xs rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-accent bg-slate-50 dark:bg-slate-900/60 px-3 py-1.5 whitespace-pre-wrap break-all"
            title="Regular expression"
          >
            {f.value}
          </div>
        ))}
      </div>
    </div>
  );
}

function WhitespaceGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Whitespace" />
      <span className="inline-block font-mono text-xs px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
        {facets[0].value}
      </span>
    </div>
  );
}

function OtherGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Other" />
      <ul className="space-y-0.5">
        {facets.map((f, i) => (
          <li key={`${f.kind}-${i}`} className="font-mono text-xs">
            <span className="text-slate-500">{f.kind}</span> ={" "}
            <span className="text-emerald-700 dark:text-emerald-300">{f.value}</span>
            {f.fixed && <span className="text-slate-500 ml-1">(fixed)</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
