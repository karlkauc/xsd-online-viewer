import { useEffect, useMemo, useState } from "react";
import { fetchContentPages, listIso20022Messages, type Iso20022Catalog, type Iso20022Message } from "../api/client";

interface Iso20022MessagesProps {
  onSelect: (id: string) => void;
  busy: boolean;
}

/** One message definition (pain.001.001) with its versions, newest first. */
interface MessageGroup {
  key: string;
  message: string;
  name: string;
  root: string;
  areaLabel: string;
  versions: Iso20022Message[];
}

type ListState = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; catalog: Iso20022Catalog };

function groupMessages(messages: Iso20022Message[]): MessageGroup[] {
  const groups = new Map<string, MessageGroup>();
  for (const m of messages) {
    const key = `${m.message}.${m.variant}`;
    let group = groups.get(key);
    if (!group) {
      group = { key, message: m.message, name: m.name, root: m.root, areaLabel: m.area_label, versions: [] };
      groups.set(key, group);
    }
    group.versions.push(m);
  }
  for (const g of groups.values()) {
    g.versions.sort((a, b) => Number(b.version) - Number(a.version));
    // The newest version's name and root describe the message best.
    g.name = g.versions[0].name;
    g.root = g.versions[0].root;
  }
  return [...groups.values()].sort((a, b) => a.key.localeCompare(b.key));
}

function matches(group: MessageGroup, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return (
    group.key.includes(q) ||
    group.name.toLowerCase().includes(q) ||
    group.root.toLowerCase().includes(q) ||
    group.versions.some((v) => v.id.includes(q))
  );
}

/**
 * The "ISO 20022" tab: every message of the pinned public mirror
 * (backend/app/standards/iso20022_catalog.json), searchable; a version chip
 * loads that schema. `?q=` prefills the search (links from the content pages).
 */
export function Iso20022Messages({ onSelect, busy }: Iso20022MessagesProps) {
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get("q") ?? "");
  const [pages, setPages] = useState<Set<string>>(new Set());

  useEffect(() => {
    listIso20022Messages()
      .then((catalog) => setState({ kind: "ready", catalog }))
      .catch((err) => setState({ kind: "error", message: err instanceof Error ? err.message : String(err) }));
    void fetchContentPages().then(setPages);
  }, []);

  const groups = useMemo(() => (state.kind === "ready" ? groupMessages(state.catalog.messages) : []), [state]);
  const shown = useMemo(() => groups.filter((g) => matches(g, query.trim())), [groups, query]);
  const areas = useMemo(() => {
    const byArea = new Map<string, MessageGroup[]>();
    for (const g of shown) byArea.set(g.areaLabel, [...(byArea.get(g.areaLabel) ?? []), g]);
    return [...byArea.entries()];
  }, [shown]);

  return (
    <div className="panel rounded-lg p-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-3">
        <input
          type="search"
          className="flex-1 min-w-0 px-2.5 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm"
          placeholder="Search: pain.001, statement, BkToCstmrStmt …"
          aria-label="Search ISO 20022 messages"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {state.kind === "ready" && (
          <span className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
            {shown.length} of {groups.length} messages
          </span>
        )}
      </div>

      {state.kind === "loading" && <p className="text-sm text-slate-500 dark:text-slate-400 py-4">Loading messages…</p>}
      {state.kind === "error" && (
        <p className="text-sm text-red-600 dark:text-red-400 py-3" role="alert">
          Could not load the message list: {state.message}
        </p>
      )}
      {state.kind === "ready" && shown.length === 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400 py-4">No message matches “{query}”.</p>
      )}

      {areas.length > 0 && (
        <div className="max-h-[60vh] overflow-y-auto -mx-1 px-1">
          {areas.map(([area, list]) => (
            <section key={area} className="mb-4">
              <h3 className="sticky top-0 bg-white dark:bg-slate-900 py-1 text-[10.5px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                {area}
              </h3>
              <ul className="divide-y divide-slate-100 dark:divide-slate-900">
                {list.map((g) => {
                  const page = `standards/iso-20022/${g.message.replace(".", "-")}`;
                  return (
                    <li key={g.key} className="py-2">
                      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                        <span className="font-mono font-medium">{g.key}</span>
                        <span>{g.name}</span>
                        <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{g.root}</span>
                        {pages.has(page) && (
                          <a className="text-xs text-accent hover:underline" href={`/${page}`}>
                            About
                          </a>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {g.versions.map((v, i) => (
                          <button
                            key={v.id}
                            type="button"
                            className={
                              "px-2 py-0.5 touch:py-1.5 rounded text-xs font-mono border " +
                              (i === 0
                                ? "border-accent text-accent hover:bg-blue-50 dark:hover:bg-blue-950/30"
                                : "border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800")
                            }
                            disabled={busy}
                            title={`Load ${v.id}${i === 0 ? " (latest)" : ""}`}
                            onClick={() => onSelect(v.id)}
                          >
                            .{v.version}
                          </button>
                        ))}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      {state.kind === "ready" && (
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Schemas load unchanged from the public mirror{" "}
          <a className="text-accent hover:underline" href={`https://github.com/${state.catalog.source.repo}/tree/${state.catalog.source.commit}/xsd`} target="_blank" rel="noopener noreferrer">
            {state.catalog.source.repo}
          </a>
          ; the authoritative source is the{" "}
          <a className="text-accent hover:underline" href={state.catalog.source.official} target="_blank" rel="noopener noreferrer">
            ISO 20022 message catalogue
          </a>
          .
        </p>
      )}
    </div>
  );
}
