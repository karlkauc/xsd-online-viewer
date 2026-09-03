import { useCallback, useEffect, useMemo, useState } from "react";
import { Uploader } from "./components/Uploader";
import { TreeView } from "./components/TreeView/TreeView";
import { DetailPanel } from "./components/DetailPanel";
import { SearchPalette } from "./components/SearchPalette";
import { AboutDialog, GITHUB_REPO_URL, openAbout } from "./components/AboutDialog";
import { FeedbackDialog } from "./components/FeedbackDialog";
import { SampleXmlDialog } from "./components/SampleXmlDialog";
import { openFeedback } from "./components/UploadError";
import { DiagramView } from "./components/DiagramView/DiagramView";
import { TextView } from "./components/TextView/TextView";
import { ValidationPanel } from "./components/ValidationPanel/ValidationPanel";
import { ContentModelView } from "./components/ContentModelView/ContentModelView";
import { Breadcrumb } from "./components/Breadcrumb";
import { XPathBar } from "./components/XPathBar";
import { Diagnostics } from "./components/Diagnostics";
import { ThemeToggle } from "./components/ThemeToggle";
import { XML_VIEWER_URL } from "./lib/uploadErrors";
import { MobileNav, type MobilePane } from "./components/MobileNav";
import { HeaderActions, type HeaderAction } from "./components/HeaderActions";
import { LG_QUERY, MD_QUERY, useMediaQuery } from "./lib/useMediaQuery";
import { useSelection, type ViewTab } from "./stores/selectionStore";
import { exportHtmlUrl } from "./api/client";
import { readHashSelection, writeHashSelection } from "./lib/deepLink";
import { API_DOCS_DESCRIPTION, API_DOCS_PATH, API_DOCS_TITLE, isApiDocsRoute } from "./lib/modeRoute";
import { ApiDocsPage } from "./components/ApiDocsPage";

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
  const docsRoute = isApiDocsRoute();

  const [structureCollapsed, setStructureCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("xsdv:structureCollapsed") === "1";
  });

  // Below `md` (phones): which single pane is visible. Between `md` and `lg`
  // (tablets): "details" means the details drawer is open, anything else means
  // closed. Unused from `lg` up, where all three panes show side by side.
  const [mobilePane, setMobilePane] = useState<MobilePane>("view");
  const detailsOpen = mobilePane === "details";
  const atLeastMd = useMediaQuery(MD_QUERY);
  const wide = useMediaQuery(LG_QUERY);

  useEffect(() => {
    window.localStorage.setItem("xsdv:structureCollapsed", structureCollapsed ? "1" : "0");
  }, [structureCollapsed]);

  // Per-route <title>/description/canonical so search engines index the
  // docs page distinctly from the viewer (the SPA shell is otherwise identical).
  useEffect(() => {
    if (!docsRoute) return;
    const previousTitle = document.title;
    const meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    const canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    const previousDescription = meta?.content ?? "";
    const previousCanonical = canonical?.href ?? "";
    document.title = API_DOCS_TITLE;
    if (meta) meta.content = API_DOCS_DESCRIPTION;
    if (canonical) canonical.href = `${window.location.origin}${API_DOCS_PATH}`;
    return () => {
      document.title = previousTitle;
      if (meta) meta.content = previousDescription;
      if (canonical) canonical.href = previousCanonical;
    };
  }, [docsRoute]);

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

  // A freshly loaded schema opens on the View pane (the diagram), matching
  // the desktop default tab.
  useEffect(() => {
    if (schemaId) setMobilePane("view");
  }, [schemaId]);

  // On phones, selecting a node jumps to the View pane so the user sees it.
  // Tablets show structure and view side by side, so leave the panes alone
  // there (closing the drawer on every selection would fight the user).
  useEffect(() => {
    if (selectedId && !atLeastMd) setMobilePane("view");
  }, [selectedId, atLeastMd]);

  // Secondary header actions: inline buttons on wide screens, a "More" menu
  // below `lg` so the header can never overflow the viewport.
  const secondaryActions = useMemo<HeaderAction[]>(
    () => [
      ...(schemaId
        ? [
            {
              key: "export-html",
              label: "Export HTML",
              title: "Export the schema as a standalone HTML page",
              href: exportHtmlUrl(schemaId),
              external: true,
            },
          ]
        : []),
      {
        key: "feedback",
        label: "💬 Feedback",
        title: "Send feedback",
        ariaLabel: "Send feedback",
        onClick: () => openFeedback(),
      },
      {
        key: "xml-viewer",
        label: "XML Viewer ↗",
        title: "Have an XML document instead? Open our sister tool XML Viewer",
        ariaLabel: "Open XML Viewer (sister tool for XML documents)",
        href: XML_VIEWER_URL,
        external: true,
      },
      {
        key: "api",
        label: docsRoute ? "← Viewer" : "API",
        title: docsRoute
          ? "Back to the viewer"
          : "Validate XML against an XSD from the command line (curl, PowerShell, Python)",
        ariaLabel: docsRoute ? "Back to the viewer" : "API documentation",
        href: docsRoute ? "/" : API_DOCS_PATH,
      },
      {
        key: "github",
        label: "GitHub",
        title: "Source code on GitHub",
        ariaLabel: "Source code on GitHub",
        href: GITHUB_REPO_URL,
        external: true,
      },
      {
        key: "about",
        label: "ℹ️ About",
        title: "About this app",
        ariaLabel: "About this app",
        onClick: () => openAbout(),
      },
    ],
    [schemaId, docsRoute],
  );

  const onSwitchTab = useCallback(
    (tab: ViewTab) => {
      setActiveTab(tab);
      setMobilePane("view");
    },
    [setActiveTab],
  );

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between gap-2 md:gap-3 px-3 md:px-4 py-2 md:py-3 short:py-1 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
        <div className="flex items-center gap-3 min-w-0">
          <h1 className="text-base md:text-lg font-semibold shrink-0">Online XSD Viewer</h1>
          {model?.target_namespace && (
            <span className="hidden lg:inline min-w-0 text-sm font-mono text-slate-500 dark:text-slate-400 truncate">
              {model.target_namespace}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 md:gap-2 shrink-0">
          {model && (
            <button
              type="button"
              className="btn"
              onClick={() => clearSchema()}
              title="Drop the current schema and load a different file"
              aria-label="Load a different schema file"
            >
              <span aria-hidden="true">📂</span>
              <span className="hidden sm:inline">Load new…</span>
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
              ⚠️ {diagnosticsCount}
              <span className="hidden sm:inline"> diagnostic{diagnosticsCount === 1 ? "" : "s"}</span>
            </button>
          )}
          <button
            type="button"
            className="btn"
            onClick={() => window.dispatchEvent(new CustomEvent("xsdv:open-search"))}
            disabled={!model}
            title="Search (Ctrl/Cmd-K)"
            aria-label="Search"
          >
            <span aria-hidden="true">🔍</span>
            <span className="hidden sm:inline">Search</span>
          </button>
          <HeaderActions actions={secondaryActions} inline={wide} />
          <ThemeToggle />
        </div>
      </header>

      {docsRoute ? (
        <main className="flex-1 min-h-0">
          <ApiDocsPage />
        </main>
      ) : !model ? (
        <main className="flex-1 overflow-auto">
          <Uploader />
        </main>
      ) : (
        <main className="flex-1 flex flex-col min-h-0">
          <div className="flex flex-col md:flex-row md:items-center gap-1 md:gap-3 px-3 md:px-4 pt-2 short:pt-1 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
            <button
              type="button"
              className="hidden md:inline-flex shrink-0 mb-1.5 items-center justify-center w-7 h-7 touch:w-9 touch:h-9 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-800"
              onClick={() => setStructureCollapsed((v) => !v)}
              title={structureCollapsed ? "Show structure" : "Hide structure"}
              aria-label={structureCollapsed ? "Show structure panel" : "Hide structure panel"}
              aria-pressed={!structureCollapsed}
            >
              <span aria-hidden="true" className="text-base leading-none">
                {structureCollapsed ? "»" : "«"}
              </span>
            </button>
            <div className="flex items-center gap-1 shrink-0 overflow-x-auto">
              {(Object.keys(TAB_LABELS) as ViewTab[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  className={
                    "px-3 py-1.5 touch:py-2 short:py-0.5 text-sm font-medium rounded-t-md border-b-2 whitespace-nowrap " +
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
            <div className="min-w-0 flex-1 flex items-center gap-2 pb-1.5 md:pb-0">
              <div className="min-w-0 flex-1">
                <Breadcrumb />
              </div>
              {/* Tablet only: the details pane lives in a drawer. */}
              <button
                type="button"
                className="hidden md:inline-flex lg:hidden btn mb-1.5"
                onClick={() => setMobilePane(detailsOpen ? "view" : "details")}
                aria-label="Show details"
                aria-pressed={detailsOpen}
                title={detailsOpen ? "Hide the details panel" : "Show the details panel"}
              >
                📋 Details
              </button>
            </div>
          </div>

          <Diagnostics />

          <section
            className={
              // Phone: one pane at a time. Tablet (md): structure + view, details
              // in a drawer. Desktop (lg): all three columns.
              "flex-1 min-h-0 flex flex-col md:grid md:gap-0 " +
              (structureCollapsed
                ? "md:grid-cols-[1fr] lg:grid-cols-[1fr_minmax(300px,26%)]"
                : "md:grid-cols-[minmax(240px,32%)_1fr] lg:grid-cols-[minmax(260px,22%)_1fr_minmax(300px,26%)]")
            }
          >
            {/* LEFT — collapsible structure sidebar (desktop); one of three
                swappable panes on mobile. */}
            <aside
              className={
                "min-h-0 overflow-hidden border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 " +
                (structureCollapsed ? "md:hidden " : "md:block ") +
                (mobilePane === "structure" ? "flex-1" : "hidden")
              }
            >
              <TreeView />
            </aside>

            {/* CENTER — active view; Tree tab shows ContentModelView for the
                selected node, or the Schema Overview when nothing is selected. */}
            <section
              className={
                "min-h-0 overflow-hidden flex-col md:flex " +
                (mobilePane === "view" ? "flex flex-1" : "hidden")
              }
            >
              {activeTab === "tree" && <XPathBar />}
              <div className="flex-1 min-h-0">
                {activeTab === "tree" && (selectedId ? <ContentModelView /> : <EmptyOverview />)}
                {activeTab === "diagram" && <DiagramView />}
                {activeTab === "text" && <TextView />}
                {activeTab === "validation" && <ValidationPanel />}
              </div>
            </section>

            {/* RIGHT — details: swappable pane on phones, slide-over drawer on
                tablets, always-visible third column on desktop. */}
            {detailsOpen && (
              <div
                className="hidden md:block lg:hidden fixed inset-0 z-20 bg-black/30"
                aria-hidden="true"
                onClick={() => setMobilePane("view")}
              />
            )}
            <aside
              className={
                "min-h-0 overflow-hidden flex-col bg-white dark:bg-slate-950 border-slate-200 dark:border-slate-800 " +
                (detailsOpen
                  ? "flex flex-1 md:flex-none md:fixed md:inset-y-0 md:right-0 md:z-30 md:w-[400px] md:max-w-[90vw] md:border-l md:shadow-2xl "
                  : "hidden ") +
                "lg:flex lg:static lg:inset-auto lg:z-auto lg:w-auto lg:max-w-none lg:shadow-none lg:border-l"
              }
            >
              <div className="hidden md:flex lg:hidden items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Details
                </span>
                <button
                  type="button"
                  className="btn px-2.5"
                  onClick={() => setMobilePane("view")}
                  aria-label="Close details"
                  title="Close details"
                >
                  ✕
                </button>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <DetailPanel />
              </div>
            </aside>
          </section>

          <MobileNav pane={mobilePane} onChange={setMobilePane} />
        </main>
      )}

      <SearchPalette />
      <FeedbackDialog />
      <AboutDialog />
      <SampleXmlDialog />
    </div>
  );
}
