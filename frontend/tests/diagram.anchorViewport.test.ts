import { describe, expect, it } from "vitest";
import { computeAnchoredViewport } from "../src/components/DiagramView/anchorViewport";

describe("computeAnchoredViewport", () => {
  it("returns the same viewport when the node has not moved", () => {
    const result = computeAnchoredViewport(
      { worldX: 100, worldY: 200 },
      { x: 100, y: 200 },
      { x: 50, y: 60, zoom: 1 },
    );
    expect(result).toEqual({ x: 50, y: 60, zoom: 1 });
  });

  it("shifts viewport by dy when node moves down at zoom=1", () => {
    // Node was at y=0, after expand it's at y=300 — viewport must move
    // down by 300 so the node stays at the same screen position.
    const result = computeAnchoredViewport(
      { worldX: 0, worldY: 0 },
      { x: 0, y: 300 },
      { x: 0, y: 0, zoom: 1 },
    );
    expect(result).toEqual({ x: 0, y: -300, zoom: 1 });
  });

  it("scales the compensation by zoom", () => {
    const result = computeAnchoredViewport(
      { worldX: 0, worldY: 0 },
      { x: 0, y: 300 },
      { x: 0, y: 0, zoom: 0.5 },
    );
    expect(result).toEqual({ x: 0, y: -150, zoom: 0.5 });
  });

  it("handles negative deltas symmetrically (collapse pulls node up)", () => {
    // Collapse: node was at y=300, now at y=0 → viewport shifts up so the
    // now-higher node stays at the same on-screen position.
    const result = computeAnchoredViewport(
      { worldX: 0, worldY: 300 },
      { x: 0, y: 0 },
      { x: 0, y: -300, zoom: 1 },
    );
    expect(result).toEqual({ x: 0, y: 0, zoom: 1 });
  });

  it("compensates both axes independently", () => {
    const result = computeAnchoredViewport(
      { worldX: 10, worldY: 20 },
      { x: 40, y: 120 },
      { x: 5, y: 7, zoom: 2 },
    );
    // dx = 10 - 40 = -30, dy = 20 - 120 = -100; scaled by zoom=2
    expect(result).toEqual({ x: 5 + -60, y: 7 + -200, zoom: 2 });
  });

  it("preserves zoom unchanged", () => {
    const result = computeAnchoredViewport(
      { worldX: 0, worldY: 0 },
      { x: 100, y: 100 },
      { x: 0, y: 0, zoom: 1.75 },
    );
    expect(result.zoom).toBe(1.75);
  });
});
