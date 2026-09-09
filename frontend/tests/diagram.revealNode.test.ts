import { describe, expect, it } from "vitest";
import type { Node } from "@xyflow/react";
import { findNodeForSelection, nodeCenter } from "../src/components/DiagramView/revealNode";

const nodes = [
  { id: "n1", position: { x: 0, y: 0 }, width: 200, height: 60, data: { schemaId: "element:A" } },
  { id: "c1", position: { x: 260, y: 0 }, width: 40, height: 40, data: { kind: "sequence" } },
  { id: "n2", position: { x: 340, y: 100 }, width: 200, height: 80, data: { schemaId: "element:B" } },
] as Node[];

describe("findNodeForSelection", () => {
  it("returns the node whose schemaId matches the selection", () => {
    expect(findNodeForSelection(nodes, "element:B", new Map())?.id).toBe("n2");
  });

  it("walks up parentById when the selection has no node of its own", () => {
    // An attribute never gets a diagram node; its host element does.
    const parentById = new Map([
      ["attribute:B/@x", "complexType:BType"],
      ["complexType:BType", "element:B"],
    ]);
    expect(findNodeForSelection(nodes, "attribute:B/@x", parentById)?.id).toBe("n2");
  });

  it("returns null when neither the selection nor any ancestor is in the graph", () => {
    const parentById = new Map([["element:Z", "element:Y"]]);
    expect(findNodeForSelection(nodes, "element:Z", parentById)).toBeNull();
  });

  it("returns null for an empty selection", () => {
    expect(findNodeForSelection(nodes, null, new Map())).toBeNull();
  });

  it("terminates on a parent cycle", () => {
    const parentById = new Map([
      ["element:Z", "element:Y"],
      ["element:Y", "element:Z"],
    ]);
    expect(findNodeForSelection(nodes, "element:Z", parentById)).toBeNull();
  });
});

describe("nodeCenter", () => {
  it("returns the world-space midpoint from position and size", () => {
    expect(nodeCenter(nodes[2])).toEqual({ x: 440, y: 140 });
  });
});
