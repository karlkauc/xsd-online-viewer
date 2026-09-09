import type { FitViewOptions, Node } from "@xyflow/react";

export const FULL_FIT: FitViewOptions = { padding: 0.2, maxZoom: 1.2, duration: 250 };

function nodeFit(node: Node): FitViewOptions {
  return { nodes: [{ id: node.id }], padding: 0.3, minZoom: 0.75, maxZoom: 1.2, duration: 250 };
}

/**
 * Initial viewport when the diagram mounts (schema load or tab switch).
 * With a selection that has a node in the graph we centre on it at a legible
 * zoom, so navigating in the Tree tab and then opening the Diagram tab lands
 * on the selected node. Otherwise desktop fits the whole graph; compact
 * viewports would shrink that to an unreadable ~0.3 zoom, so they centre on
 * the first root instead and let the user pan/pinch from there.
 */
export function initialFitOptions(
  nodes: Node[],
  selectedId: string | null,
  compact: boolean,
): FitViewOptions {
  if (nodes.length === 0) return FULL_FIT;
  const selected = nodes.find(
    (n) => (n.data as { schemaId?: string } | undefined)?.schemaId === selectedId,
  );
  if (selected) return nodeFit(selected);
  return compact ? nodeFit(nodes[0]) : FULL_FIT;
}
