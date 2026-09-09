// Locates the diagram node that should be brought into view for a
// selection made outside the diagram (XPath breadcrumb, constraint links,
// search). Attributes, anonymous types and other declarations never get a
// node of their own, so we climb `parentById` until an ancestor that does.

import type { Node } from "@xyflow/react";

const MAX_CLIMB = 32;

function nodeFor(nodes: Node[], schemaId: string): Node | undefined {
  return nodes.find((n) => (n.data as { schemaId?: string } | undefined)?.schemaId === schemaId);
}

export function findNodeForSelection(
  nodes: Node[],
  selectedId: string | null,
  parentById: Map<string, string>,
): Node | null {
  let cur: string | undefined = selectedId ?? undefined;
  const seen = new Set<string>();
  for (let i = 0; cur && i < MAX_CLIMB; i++) {
    if (seen.has(cur)) break;
    seen.add(cur);
    const hit = nodeFor(nodes, cur);
    if (hit) return hit;
    cur = parentById.get(cur);
  }
  return null;
}

/** World-space midpoint; buildGraph sets explicit width/height on every node. */
export function nodeCenter(node: Node): { x: number; y: number } {
  return {
    x: node.position.x + (node.width ?? 0) / 2,
    y: node.position.y + (node.height ?? 0) / 2,
  };
}
