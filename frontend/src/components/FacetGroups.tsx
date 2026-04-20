import { Fragment } from "react";
import type { Facet, FacetKind, SimpleType } from "../types/schema";

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

export interface FacetGroupsProps {
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
