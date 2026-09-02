import { describe, expect, it } from "vitest";
import type { Node } from "@xyflow/react";
import { initialFitOptions } from "../src/components/DiagramView/fitOptions";

const nodes = [
  { id: "n1", position: { x: 0, y: 0 }, data: { schemaId: "element:A" } },
  { id: "n2", position: { x: 300, y: 0 }, data: { schemaId: "element:B" } },
] as Node[];

describe("initialFitOptions", () => {
  it("fits the whole graph on wide viewports", () => {
    const opts = initialFitOptions(nodes, "element:B", false);
    expect(opts.nodes).toBeUndefined();
    expect(opts.padding).toBe(0.2);
    expect(opts.maxZoom).toBe(1.2);
  });

  it("fits the selected node at a readable zoom on compact viewports", () => {
    const opts = initialFitOptions(nodes, "element:B", true);
    expect(opts.nodes).toEqual([{ id: "n2" }]);
    expect(opts.minZoom).toBeGreaterThanOrEqual(0.75);
    expect(opts.maxZoom).toBe(1.2);
  });

  it("falls back to the first node when nothing is selected", () => {
    const opts = initialFitOptions(nodes, null, true);
    expect(opts.nodes).toEqual([{ id: "n1" }]);
  });

  it("fits everything when the graph is empty", () => {
    const opts = initialFitOptions([], null, true);
    expect(opts.nodes).toBeUndefined();
  });
});
