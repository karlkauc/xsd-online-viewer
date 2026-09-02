import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
} from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useSelection } from "../../stores/selectionStore";
import { buildDiagramGraph } from "./buildGraph";
import { ElementNode } from "./ElementNode";
import { CompositorNode } from "./CompositorNode";
import { exportFlowAsPng, exportFlowAsSvg } from "./exportImage";
import { collectExpandableElementIds } from "../../lib/expandAll";
import { computeAnchoredViewport } from "./anchorViewport";
import { DiagramToolbar } from "./DiagramToolbar";
import { initialFitOptions } from "./fitOptions";
import { MD_QUERY, useMediaQuery } from "../../lib/useMediaQuery";

const NODE_TYPES = {
  element: ElementNode as unknown as React.ComponentType<NodeProps>,
  compositor: CompositorNode as unknown as React.ComponentType<NodeProps>,
};

// Minimap colors chosen for WCAG 2.1 AA on non-text UI (>= 3:1). Light pair
// reaches ~7.5:1, dark pair ~10:1 — both comfortably pass.
const MINIMAP_LIGHT = {
  nodeColor: "#475569",
  nodeStrokeColor: "#1e293b",
  maskColor: "rgba(15, 23, 42, 0.12)",
  bgColor: "#ffffff",
} as const;
const MINIMAP_DARK = {
  nodeColor: "#cbd5e1",
  nodeStrokeColor: "#f1f5f9",
  maskColor: "rgba(226, 232, 240, 0.15)",
  bgColor: "#0f172a",
} as const;

function subscribeToHtmlClass(callback: () => void): () => void {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => observer.disconnect();
}
function getIsDark(): boolean {
  return document.documentElement.classList.contains("dark");
}
function useIsDarkTheme(): boolean {
  return useSyncExternalStore(subscribeToHtmlClass, getIsDark, () => false);
}

export function DiagramView() {
  return (
    <ReactFlowProvider>
      <DiagramInner />
    </ReactFlowProvider>
  );
}

function DiagramInner() {
  const model = useSelection((s) => s.model);
  const selectedId = useSelection((s) => s.selectedId);
  const expandedIds = useSelection((s) => s.expandedIds);
  const setSelected = useSelection((s) => s.setSelected);
  const toggleExpanded = useSelection((s) => s.toggleExpanded);
  const setExpandedIds = useSelection((s) => s.setExpandedIds);
  const minimapVisible = useSelection((s) => s.minimapVisible);
  const setMinimapVisible = useSelection((s) => s.setMinimapVisible);

  const { nodes, edges } = useMemo<{ nodes: Node[]; edges: Edge[] }>(() => {
    if (!model) return { nodes: [], edges: [] };
    return buildDiagramGraph(model, expandedIds, selectedId);
  }, [model, expandedIds, selectedId]);

  const flow = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const isDark = useIsDarkTheme();
  const minimapColors = isDark ? MINIMAP_DARK : MINIMAP_LIGHT;
  const compact = !useMediaQuery(MD_QUERY);

  // Latest fit options without re-running the fit effects on every render.
  const fitOptionsRef = useRef(initialFitOptions(nodes, selectedId, compact));
  fitOptionsRef.current = initialFitOptions(nodes, selectedId, compact);

  // Remembers where the clicked node sat in world-space before a
  // toggle-driven re-layout, so we can translate the viewport afterwards
  // and keep the node visually fixed on screen.
  const pendingAnchorRef = useRef<
    { schemaId: string; worldX: number; worldY: number } | null
  >(null);

  // Only re-fit when the schema changes. Re-fitting on every expand/collapse
  // jitters the viewport and loses the user's pan/zoom state.
  useEffect(() => {
    if (nodes.length > 0) {
      requestAnimationFrame(() => flow.fitView(fitOptionsRef.current));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.schema_id]);

  // On mobile the diagram can mount inside a hidden (display:none) pane, so
  // React Flow's initial fitView measures a 0x0 box. Re-fit the first time the
  // container gains real size. Inert on desktop, where it has size from mount.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    let hadSize = el.clientWidth > 0 && el.clientHeight > 0;
    const observer = new ResizeObserver(() => {
      const hasSize = el.clientWidth > 0 && el.clientHeight > 0;
      if (!hadSize && hasSize && nodes.length > 0) {
        requestAnimationFrame(() => flow.fitView(fitOptionsRef.current));
      }
      hadSize = hasSize;
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [flow, nodes.length]);

  useLayoutEffect(() => {
    const anchor = pendingAnchorRef.current;
    if (!anchor) return;
    pendingAnchorRef.current = null;
    const newNode = nodes.find(
      (n) => (n.data as { schemaId?: string } | undefined)?.schemaId === anchor.schemaId,
    );
    if (!newNode) return;
    const next = computeAnchoredViewport(
      { worldX: anchor.worldX, worldY: anchor.worldY },
      newNode.position,
      flow.getViewport(),
    );
    flow.setViewport(next);
  }, [nodes, flow]);

  const onNodeClick = useCallback(
    (_e: unknown, node: Node) => {
      const data = node.data as { schemaId?: string; expandable?: boolean } | undefined;
      if (!data?.schemaId) return;
      setSelected(data.schemaId);
      if (data.expandable) {
        pendingAnchorRef.current = {
          schemaId: data.schemaId,
          worldX: node.position.x,
          worldY: node.position.y,
        };
        toggleExpanded(data.schemaId);
      }
    },
    [setSelected, toggleExpanded],
  );

  const onExport = useCallback(
    async (format: "png" | "svg") => {
      const viewportEl =
        wrapperRef.current?.querySelector<HTMLElement>(".react-flow__viewport");
      if (!viewportEl) return;
      const exportNodes = flow.getNodes();
      try {
        if (format === "svg") {
          await exportFlowAsSvg(viewportEl, exportNodes, { filename: "schema-diagram.svg" });
        } else {
          await exportFlowAsPng(viewportEl, exportNodes, { filename: "schema-diagram.png" });
        }
      } catch (err) {
        console.error(`Diagram ${format.toUpperCase()} export failed:`, err);
        const msg = err instanceof Error ? err.message : String(err);
        alert(`${format.toUpperCase()} export failed: ${msg}`);
      }
    },
    [flow],
  );

  const onExpandAll = useCallback(() => {
    if (!model) return;
    setExpandedIds(collectExpandableElementIds(model));
  }, [model, setExpandedIds]);

  const onCollapseAll = useCallback(() => {
    setExpandedIds(new Set());
  }, [setExpandedIds]);

  return (
    <div ref={wrapperRef} className="relative h-full w-full">
      <DiagramToolbar
        compact={compact}
        minimapVisible={minimapVisible}
        canExpand={!!model}
        canCollapse={expandedIds.size > 0}
        onExpandAll={onExpandAll}
        onCollapseAll={onCollapseAll}
        onToggleMinimap={() => setMinimapVisible(!minimapVisible)}
        onExport={onExport}
      />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={onNodeClick}
        fitView
        minZoom={0.2}
        // Themes the stock controls/background; the minimap colours above
        // are our own because the defaults are too faint.
        colorMode={isDark ? "dark" : "light"}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} />
        {minimapVisible && (
          <MiniMap pannable zoomable nodeStrokeWidth={2} {...minimapColors} />
        )}
        <Controls />
      </ReactFlow>
    </div>
  );
}
