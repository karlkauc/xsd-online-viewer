import { describe, expect, it } from "vitest";
import type { Node } from "@xyflow/react";
import { buildDiagramGraph } from "../src/components/DiagramView/buildGraph";
import {
  wildcardExtensionModel,
  HEADER_ID,
  NEXT_VERSION_ID,
  EXTENSION_ID,
} from "./fixtures/wildcardExtensionModel";

function byLabel(nodes: Node[], label: string): Node {
  const hit = nodes.find(
    (n) => n.type === "element" && (n.data as { label: string }).label === label,
  );
  if (!hit) throw new Error(`element node ${label} missing`);
  return hit;
}

function box(node: Node): { top: number; bottom: number; x: number } {
  if (typeof node.height !== "number") throw new Error(`node ${node.id} has no height`);
  return {
    top: node.position.y,
    bottom: node.position.y + node.height,
    x: node.position.x,
  };
}

// GLEIF LEI-CDF 3.1: `Extension` is a documented, optional element whose type
// is nothing but `<xs:sequence><xs:any/></xs:sequence>`. Its expanded subtree
// (compositor + wildcard, 40px each) is shorter than the element node itself,
// so centring the element on that subtree used to lift it above the Y band the
// parent sequence had allotted it — straight over the sibling above.
describe("expanding an element whose content is shorter than the element", () => {
  it("never lifts the element above the band its parent allotted", () => {
    const expanded = new Set([HEADER_ID, EXTENSION_ID]);
    const { nodes } = buildDiagramGraph(wildcardExtensionModel, expanded, null);

    const nextVersion = box(byLabel(nodes, "NextVersion"));
    const extension = box(byLabel(nodes, "Extension"));

    expect(extension.x).toBe(nextVersion.x);
    expect(extension.top).toBeGreaterThanOrEqual(nextVersion.bottom);
  });

  it("keeps every sibling column free of overlap for both expansions", () => {
    const expanded = new Set([HEADER_ID, NEXT_VERSION_ID, EXTENSION_ID]);
    const { nodes } = buildDiagramGraph(wildcardExtensionModel, expanded, null);

    const byColumn = new Map<number, Node[]>();
    for (const node of nodes) {
      const list = byColumn.get(node.position.x) ?? [];
      list.push(node);
      byColumn.set(node.position.x, list);
    }
    for (const [x, column] of byColumn) {
      const boxes = column.map(box).sort((a, b) => a.top - b.top);
      for (let i = 1; i < boxes.length; i++) {
        expect(
          boxes[i].top,
          `column x=${x}: node ${i} starts above the previous node's bottom`,
        ).toBeGreaterThanOrEqual(boxes[i - 1].bottom);
      }
    }
  });
});
