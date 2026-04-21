// Expanding/collapsing a node in the diagram reflows the layout, and the
// clicked node itself may move in world-space (it gets centered on its
// children). To keep the node visually fixed on screen, we translate the
// viewport by the node's world-space delta scaled by the current zoom.

export interface Anchor {
  worldX: number;
  worldY: number;
}

export interface WorldPos {
  x: number;
  y: number;
}

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

export function computeAnchoredViewport(
  anchor: Anchor,
  newWorldPos: WorldPos,
  viewport: Viewport,
): Viewport {
  const dx = anchor.worldX - newWorldPos.x;
  const dy = anchor.worldY - newWorldPos.y;
  return {
    x: viewport.x + dx * viewport.zoom,
    y: viewport.y + dy * viewport.zoom,
    zoom: viewport.zoom,
  };
}
