import { useCallback, useEffect, useMemo, useRef } from "react";
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

const NODE_TYPES = {
  element: ElementNode as unknown as React.ComponentType<NodeProps>,
  compositor: CompositorNode as unknown as React.ComponentType<NodeProps>,
};

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

  const { nodes, edges } = useMemo<{ nodes: Node[]; edges: Edge[] }>(() => {
    if (!model) return { nodes: [], edges: [] };
    return buildDiagramGraph(model, expandedIds, selectedId);
  }, [model, expandedIds, selectedId]);

  const flow = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  // Only re-fit when the schema changes. Re-fitting on every expand/collapse
  // jitters the viewport and loses the user's pan/zoom state.
  useEffect(() => {
    if (nodes.length > 0) {
      requestAnimationFrame(() =>
        flow.fitView({ padding: 0.2, duration: 250, maxZoom: 1.2 }),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.schema_id]);

  const onNodeClick = useCallback(
    (_e: unknown, node: Node) => {
      const data = node.data as { schemaId?: string; expandable?: boolean } | undefined;
      if (!data?.schemaId) return;
      setSelected(data.schemaId);
      if (data.expandable) toggleExpanded(data.schemaId);
    },
    [setSelected, toggleExpanded],
  );

  const onExport = useCallback(
    async (format: "png" | "svg") => {
      const node = wrapperRef.current?.querySelector<HTMLElement>(".react-flow");
      if (!node) return;
      if (format === "svg") exportFlowAsSvg(node, "schema-diagram.svg");
      else await exportFlowAsPng(node, "schema-diagram.png");
    },
    [],
  );

  return (
    <div ref={wrapperRef} className="relative h-full w-full">
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button type="button" className="btn" onClick={() => onExport("svg")}>
          Export SVG
        </button>
        <button type="button" className="btn" onClick={() => onExport("png")}>
          Export PNG
        </button>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={onNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}
