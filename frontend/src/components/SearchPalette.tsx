import { useEffect, useMemo, useRef, useState } from "react";
import { useSelection } from "../stores/selectionStore";
import { KindBadge } from "./TreeView/KindBadge";
import { searchableText, snippetAround } from "../lib/searchText";
import type { NodeIndexEntry } from "../types/schema";

const MAX_RESULTS = 60;

interface Hit {
  entry: NodeIndexEntry;
  /** Documentation excerpt when the match came from there, not the name. */
  snippet?: string;
}

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

  // Documentation, comments and enumeration values, lower-cased once per schema.
  const texts = useMemo(
    () => index.map((entry) => searchableText(entry.node)),
    [index],
  );

  const results = useMemo<Hit[]>(() => {
    if (!query.trim()) return index.slice(0, MAX_RESULTS).map((entry) => ({ entry }));
    const needle = query.toLowerCase();
    const scored: { hit: Hit; score: number }[] = [];
    index.forEach((entry, i) => {
      const label = entry.label.toLowerCase();
      let score = 0;
      if (label === needle) score = 5;
      else if (label.startsWith(needle)) score = 4;
      else if (label.includes(needle)) score = 3;
      else if ((entry.qname ?? "").toLowerCase().includes(needle)) score = 2;
      if (score > 0) {
        scored.push({ hit: { entry }, score });
        return;
      }
      const text = texts[i];
      if (text && text.toLowerCase().includes(needle)) {
        scored.push({ hit: { entry, snippet: snippetAround(text, query.trim()) }, score: 1 });
      }
    });
    scored.sort((a, b) => b.score - a.score || a.hit.entry.label.localeCompare(b.hit.entry.label));
    return scored.slice(0, MAX_RESULTS).map((x) => x.hit);
  }, [query, index, texts]);

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
      className="fixed inset-0 bg-black/30 flex items-start justify-center px-4 pt-4 md:pt-[10vh] z-50"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) setOpen(false);
      }}
    >
      <div className="w-full max-w-xl bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800">
        <input
          ref={inputRef}
          className="w-full px-4 py-3 bg-transparent border-b border-slate-200 dark:border-slate-800 outline-none"
          placeholder="Search names, documentation, enumeration values…"
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
              if (hit) commit(hit.entry.id);
            }
          }}
        />
        <ul className="max-h-[60dvh] md:max-h-[50vh] overflow-auto py-1">
          {results.length === 0 && (
            <li className="px-4 py-2 text-sm text-slate-500">No matches.</li>
          )}
          {results.map(({ entry, snippet }, i) => (
            <li
              key={entry.id}
              className={
                "px-4 py-2 touch:py-3 text-sm cursor-pointer " +
                (i === cursor ? "bg-blue-50 dark:bg-blue-900/30" : "")
              }
              onMouseEnter={() => setCursor(i)}
              onClick={() => commit(entry.id)}
            >
              <div className="flex items-center gap-2">
                <KindBadge kind={entry.kind} />
                <span className="font-mono">{entry.label}</span>
                <span className="text-xs text-slate-500 truncate">{entry.qname ?? ""}</span>
              </div>
              {snippet && (
                <p className="mt-0.5 pl-1 text-xs text-slate-500 dark:text-slate-400 truncate">
                  <span className="uppercase tracking-wider text-[10px] mr-1.5 text-slate-400">doc</span>
                  {snippet}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
