import { useCallback, useEffect, useState } from "react";
import { Uploader } from "./components/Uploader";
import { TreeView } from "./components/TreeView/TreeView";
import { DetailPanel } from "./components/DetailPanel";
import { SearchPalette } from "./components/SearchPalette";
import { DiagramView } from "./components/DiagramView/DiagramView";
import { TextView } from "./components/TextView/TextView";
import { ValidationPanel } from "./components/ValidationPanel/ValidationPanel";
import { ContentModelView } from "./components/ContentModelView/ContentModelView";
import { Breadcrumb } from "./components/Breadcrumb";
import { XPathBar } from "./components/XPathBar";
import { Diagnostics } from "./components/Diagnostics";
import { ThemeToggle } from "./components/ThemeToggle";
import { useSelection, type ViewTab } from "./stores/selectionStore";
import { exportHtmlUrl } from "./api/client";
import { readHashSelection, writeHashSelection } from "./lib/deepLink";

const TAB_LABELS: Record<ViewTab, string> = {
  tree: "Tree",
  diagram: "Diagram",
  text: "Text",
  validation: "Validation",
};

function EmptyOverview() {
  const model = useSelection((s) => s.model);
  const index = useSelection((s) => s.index);

  const countByKind = {
    element: index.filter((e) => e.kind === "element").length,
    complexType: index.filter((e) => e.kind === "complexType").length,
    simpleType: index.filter((e) => e.kind === "simpleType").length,
    attribute: index.filter((e) => e.kind === "attribute").length,
    group: index.filter((e) => e.kind === "group").length,
    attributeGroup: index.filter((e) => e.kind === "attributeGroup").length,
  };

  return (
    <div className="h-full overflow-auto p-8">
      <div className="max-w-xl mx-auto">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">
          Schema Overview
        </h2>
        {model?.target_namespace && (
          <p className="font-mono text-xs text-slate-500 dark:text-slate-400 mb-6 break-all">
            {model.target_namespace}
          </p>
        )}
        <dl className="grid grid-cols-2 gap-3 text-sm">
          {Object.entries(countByKind).map(([kind, n]) => (
            <div
              key={kind}
              className="flex items-baseline justify-between border-b border-slate-200 dark:border-slate-800 pb-1"
            >
              <dt className="text-slate-600 dark:text-slate-300 font-mono">{kind}</dt>
              <dd className="font-mono tabular-nums text-slate-900 dark:text-slate-100">{n}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-8 text-xs text-slate-500 dark:text-slate-400">
          Select a node in the structure panel, switch to the Diagram or Text tab, or press{" "}
          <kbd className="font-mono px-1 py-px bg-slate-100 dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700">
            ⌘K
          </kbd>{" "}
          to search.
        </p>
      </div>
    </div>
  );
}

export default function App() {
  const model = useSelection((s) => s.model);
  const schemaId = useSelection((s) => s.schemaId);
  const activeTab = useSelection((s) => s.activeTab);
  const setActiveTab = useSelection((s) => s.setActiveTab);
  const selectedId = useSelection((s) => s.selectedId);
  const setSelected = useSelection((s) => s.setSelected);
  const clearSchema = useSelection((s) => s.clearSchema);
  const diagnosticsVisible = useSelection((s) => s.diagnosticsVisible);
  const setDiagnosticsVisible = useSelection((s) => s.setDiagnosticsVisible);
  const diagnosticsCount = model?.diagnostics?.length ?? 0;

  const [structureCollapsed, setStructureCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("xsdv:structureCollapsed") === "1";
  });

  useEffect(() => {
    window.localStorage.setItem("xsdv:structureCollapsed", structureCollapsed ? "1" : "0");
  }, [structureCollapsed]);

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

  useEffect(() => {
    if (!model) return;
    const hashId = readHashSelection();
    if (hashId) setSelected(hashId);
  }, [model, setSelected]);

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
          {model && (
            <button
              type="button"
              className="btn"
              onClick={() => clearSchema()}
              title="Drop the current schema and load a different file"
              aria-label="Load a different schema file"
            >
              📂 Load new…
            </button>
          )}
          {diagnosticsCount > 0 && !diagnosticsVisible && (
            <button
              type="button"
              className="btn"
              onClick={() => setDiagnosticsVisible(true)}
              title="Show diagnostics"
              aria-label="Show diagnostics"
            >
              ⚠️ {diagnosticsCount} diagnostic{diagnosticsCount === 1 ? "" : "s"}
            </button>
          )}
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
            <a className="btn" href={exportHtmlUrl(schemaId)} target="_blank" rel="noopener noreferrer">
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
          <div className="flex items-center gap-3 px-4 pt-2 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
            <button
              type="button"
              className="shrink-0 mb-1.5 inline-flex items-center justify-center w-7 h-7 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-800"
              onClick={() => setStructureCollapsed((v) => !v)}
              title={structureCollapsed ? "Show structure" : "Hide structure"}
              aria-label={structureCollapsed ? "Show structure panel" : "Hide structure panel"}
              aria-pressed={!structureCollapsed}
            >
              <span aria-hidden="true" className="text-base leading-none">
                {structureCollapsed ? "»" : "«"}
              </span>
            </button>
            <div className="flex items-center gap-1 shrink-0">
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
            </div>
            <div className="min-w-0 flex-1">
              <Breadcrumb />
            </div>
          </div>

          <Diagnostics />

          <section
            className={
              "flex-1 min-h-0 grid gap-0 grid-cols-1 " +
              (structureCollapsed
                ? "md:grid-cols-[1fr_minmax(300px,26%)]"
                : "md:grid-cols-[minmax(260px,22%)_1fr_minmax(300px,26%)]")
            }
          >
            {/* LEFT — collapsible structure sidebar */}
            {!structureCollapsed && (
              <aside className="min-h-0 overflow-hidden border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
                <TreeView />
              </aside>
            )}

            {/* CENTER — active view; Tree tab shows ContentModelView for the
                selected node, or the Schema Overview when nothing is selected. */}
            <section className="min-h-0 overflow-hidden flex flex-col">
              {activeTab === "tree" && <XPathBar />}
              <div className="flex-1 min-h-0">
                {activeTab === "tree" && (selectedId ? <ContentModelView /> : <EmptyOverview />)}
                {activeTab === "diagram" && <DiagramView />}
                {activeTab === "text" && <TextView />}
                {activeTab === "validation" && <ValidationPanel />}
              </div>
            </section>

            {/* RIGHT — always-visible details panel */}
            <aside className="min-h-0 overflow-hidden border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
              <DetailPanel />
            </aside>
          </section>
        </main>
      )}

      <SearchPalette />
    </div>
  );
}
