import { useEffect, useMemo, useRef, useState } from "react";
import { useSelection } from "../stores/selectionStore";
import { KindBadge } from "./TreeView/KindBadge";

const MAX_RESULTS = 60;

export function SearchPalette() {
  const index = useSelection((s) => s.index);
  const setSelected = useSelection((s) => s.setSelected);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const handler = () => {
      setOpen(true);
      setQuery("");
      setCursor(0);
    };
    window.addEventListener("xsdv:open-search", handler);
    return () => window.removeEventListener("xsdv:open-search", handler);
  }, []);

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  const results = useMemo(() => {
    if (!query.trim()) return index.slice(0, MAX_RESULTS);
    const needle = query.toLowerCase();
    const scored = index
      .map((entry) => {
        const label = entry.label.toLowerCase();
        let score = 0;
        if (label === needle) score = 4;
        else if (label.startsWith(needle)) score = 3;
        else if (label.includes(needle)) score = 2;
        else if ((entry.qname ?? "").toLowerCase().includes(needle)) score = 1;
        return { entry, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score || a.entry.label.localeCompare(b.entry.label));
    return scored.slice(0, MAX_RESULTS).map((x) => x.entry);
  }, [query, index]);

  useEffect(() => {
    if (cursor >= results.length) setCursor(Math.max(0, results.length - 1));
  }, [results, cursor]);

  if (!open) return null;

  const commit = (id: string) => {
    setSelected(id);
    setOpen(false);
  };

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-start justify-center pt-[10vh] z-50"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) setOpen(false);
      }}
    >
      <div className="w-full max-w-xl bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800">
        <input
          ref={inputRef}
          className="w-full px-4 py-3 bg-transparent border-b border-slate-200 dark:border-slate-800 outline-none"
          placeholder="Search elements, types, attributes…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setCursor(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
            else if (event.key === "ArrowDown") {
              event.preventDefault();
              setCursor((c) => Math.min(c + 1, results.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              const hit = results[cursor];
              if (hit) commit(hit.id);
            }
          }}
        />
        <ul className="max-h-[50vh] overflow-auto py-1">
          {results.length === 0 && (
            <li className="px-4 py-2 text-sm text-slate-500">No matches.</li>
          )}
          {results.map((hit, i) => (
            <li
              key={hit.id}
              className={
                "px-4 py-2 text-sm flex items-center gap-2 cursor-pointer " +
                (i === cursor ? "bg-blue-50 dark:bg-blue-900/30" : "")
              }
              onMouseEnter={() => setCursor(i)}
              onClick={() => commit(hit.id)}
            >
              <KindBadge kind={hit.kind} />
              <span className="font-mono">{hit.label}</span>
              <span className="text-xs text-slate-500 truncate">{hit.qname ?? ""}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
