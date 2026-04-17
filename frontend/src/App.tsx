import { useCallback, useEffect } from "react";
import { Uploader } from "./components/Uploader";
import { TreeView } from "./components/TreeView/TreeView";
import { DetailPanel } from "./components/DetailPanel";
import { SearchPalette } from "./components/SearchPalette";
import { DiagramView } from "./components/DiagramView/DiagramView";
import { TextView } from "./components/TextView/TextView";
import { Breadcrumb } from "./components/Breadcrumb";
import { Diagnostics } from "./components/Diagnostics";
import { ThemeToggle } from "./components/ThemeToggle";
import { useSelection, type ViewTab } from "./stores/selectionStore";
import { exportHtmlUrl } from "./api/client";
import { readHashSelection, writeHashSelection } from "./lib/deepLink";

const TAB_LABELS: Record<ViewTab, string> = {
  tree: "Tree",
  diagram: "Diagram",
  text: "Text",
};

export default function App() {
  const model = useSelection((s) => s.model);
  const schemaId = useSelection((s) => s.schemaId);
  const activeTab = useSelection((s) => s.activeTab);
  const setActiveTab = useSelection((s) => s.setActiveTab);
  const selectedId = useSelection((s) => s.selectedId);
  const setSelected = useSelection((s) => s.setSelected);
  const showSidebar = activeTab === "tree";

  // Keyboard shortcut: Ctrl/Cmd-K opens the search palette. Handled via a
  // custom event so multiple components can subscribe.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        window.dispatchEvent(new CustomEvent("xsdv:open-search"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Deep-link: read selection from URL hash on load and when the schema changes.
  useEffect(() => {
    if (!model) return;
    const hashId = readHashSelection();
    if (hashId) setSelected(hashId);
  }, [model, setSelected]);

  // Deep-link: write selection into URL hash.
  useEffect(() => {
    writeHashSelection(selectedId);
  }, [selectedId]);

  const onSwitchTab = useCallback(
    (tab: ViewTab) => setActiveTab(tab),
    [setActiveTab],
  );

  return (
    <div className="flex flex-col h-full">
      <header className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">Online XSD Viewer</h1>
          {model?.target_namespace && (
            <span className="hidden md:inline text-sm font-mono text-slate-500 dark:text-slate-400">
              {model.target_namespace}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn"
            onClick={() => window.dispatchEvent(new CustomEvent("xsdv:open-search"))}
            disabled={!model}
            title="Search (Ctrl/Cmd-K)"
          >
            🔍 Search
          </button>
          {schemaId && (
            <a className="btn" href={exportHtmlUrl(schemaId)} target="_blank" rel="noreferrer">
              Export HTML
            </a>
          )}
          <ThemeToggle />
        </div>
      </header>

      {!model ? (
        <main className="flex-1 overflow-auto">
          <Uploader />
        </main>
      ) : (
        <main className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center gap-1 px-4 pt-2 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
            {(Object.keys(TAB_LABELS) as ViewTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                className={
                  "px-3 py-1.5 text-sm font-medium rounded-t-md border-b-2 " +
                  (activeTab === tab
                    ? "border-accent text-accent"
                    : "border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200")
                }
                onClick={() => onSwitchTab(tab)}
              >
                {TAB_LABELS[tab]}
              </button>
            ))}
            <div className="flex-1" />
            <Breadcrumb />
          </div>

          <Diagnostics />

          <section
            className={
              "flex-1 min-h-0 grid gap-0 " +
              (showSidebar
                ? "grid-cols-1 md:grid-cols-[minmax(280px,28%)_1fr]"
                : "grid-cols-1")
            }
          >
            {showSidebar && (
              <aside className="min-h-0 overflow-hidden border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
                <TreeView />
              </aside>
            )}
            <section className="min-h-0 overflow-hidden flex flex-col">
              <div className="flex-1 min-h-0">
                {activeTab === "tree" && <DetailPanel />}
                {activeTab === "diagram" && <DiagramView />}
                {activeTab === "text" && <TextView />}
              </div>
            </section>
          </section>
        </main>
      )}

      <SearchPalette />
    </div>
  );
}
