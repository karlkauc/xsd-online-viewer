import { useMemo } from "react";
import { useSelection } from "../stores/selectionStore";
import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  Facet,
  NodeIndexEntry,
  SchemaNode,
  SimpleType,
} from "../types/schema";
import { KindBadge } from "./TreeView/KindBadge";

export function DetailPanel() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
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
        {renderSpecifics(node)}
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

function renderSpecifics(node: SchemaNode) {
  if ("type_inline_complex" in node) return renderElement(node);
  if ("use" in node) return renderAttribute(node);
  if ("content_kind" in node) return renderComplexType(node);
  if ("facets" in node) return renderSimpleType(node);
  return null;
}

function renderElement(element: ElementDecl) {
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
    </section>
  );
}

function renderAttribute(attr: AttributeDecl) {
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
      {attr.type_inline && <FacetList title="Inline facets" facets={attr.type_inline.facets} />}
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
        <FacetList title="Simple-content facets" facets={complex.simple_content_facets} />
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
      <FacetList title="Facets" facets={simple.facets} />
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

function FacetList({ title, facets }: { title: string; facets: Facet[] }) {
  if (facets.length === 0) return null;
  return (
    <div className="mt-3">
      <h4 className="font-semibold mb-1">{title}</h4>
      <ul className="space-y-0.5">
        {facets.map((f, i) => (
          <li key={`${f.kind}-${i}`} className="font-mono text-xs">
            {f.kind} = <span className="text-emerald-700 dark:text-emerald-300">{f.value}</span>
            {f.fixed && <span className="text-slate-500 ml-1">(fixed)</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
