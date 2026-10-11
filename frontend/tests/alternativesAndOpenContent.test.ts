import { describe, expect, it } from "vitest";
import { buildTreeRows } from "../src/components/TreeView/treeRows";
import { buildDiagramGraph } from "../src/components/DiagramView/buildGraph";
import { buildIndex } from "../src/lib/indexSchema";
import { collectExpandableElementIds } from "../src/lib/expandAll";
import type { SchemaNodeKind } from "../src/types/schema";
import { alternativesModel, SHAPE_ID } from "./fixtures/alternativesModel";

const KINDS = new Set<SchemaNodeKind>(["element", "attribute", "complexType"]);

describe("tree rows for type alternatives and open content", () => {
  const { indexById } = buildIndex(alternativesModel);

  it("lists each alternative under the element, after the declared type's content", () => {
    const rows = buildTreeRows(alternativesModel, new Set([SHAPE_ID]), KINDS, indexById);
    const under = rows.slice(1, rows.findIndex((r) => r.depth === 0 && r.id !== SHAPE_ID));
    expect(under.map((r) => r.label)).toEqual(["id", "if @kind = 'circle'", "if @kind = 'square'"]);
    const circle = under[1];
    expect(circle).toMatchObject({
      wildcard: true,
      typeHint: "Circle",
      hasChildren: true,
      // A click goes to the type the alternative assigns.
      selectId: "complexType:Circle",
    });
  });

  it("shows an alternative's content, open content included, when expanded", () => {
    const circleRow = `alternative:${SHAPE_ID}:0`;
    const rows = buildTreeRows(alternativesModel, new Set([SHAPE_ID, circleRow]), KINDS, indexById);
    const at = rows.findIndex((r) => r.id === circleRow);
    expect(rows.slice(at + 1, at + 3).map((r) => r.label)).toEqual([
      "radius",
      "open: any ##other",
    ]);
    expect(rows[at + 2]).toMatchObject({
      wildcard: true,
      occurs: "0..∞",
      typeHint: "suffix · lax",
      selectId: "complexType:Circle",
    });
  });

  it("counts an alternative's type as a use of that type", () => {
    const { usagesByTarget } = buildIndex(alternativesModel);
    expect(usagesByTarget.get("Circle")?.map((e) => e.id)).toEqual([SHAPE_ID]);
  });
});

describe("diagram for type alternatives and open content", () => {
  const captions = (expanded: string[]) =>
    buildDiagramGraph(alternativesModel, new Set(expanded), null)
      .nodes.filter((n) => n.type === "compositor")
      .map((n) => (n.data as { caption?: string; kind: string }).caption ?? n.data.kind);

  it("draws the alternatives as a choice between the types, the declared one last", () => {
    const graph = buildDiagramGraph(alternativesModel, new Set([SHAPE_ID]), null);
    const labels = graph.nodes
      .filter((n) => n.type === "element")
      .map((n) => (n.data as { label: string }).label);
    expect(labels.sort()).toEqual(["Shape", "id", "radius", "side"]);
    expect(captions([SHAPE_ID])).toEqual(
      expect.arrayContaining(["type?", "Circle", "Square", "Base", "open"]),
    );
    const open = graph.nodes.find((n) => (n.data as { caption?: string }).caption === "open");
    expect((open!.data as { title: string }).title).toContain("xs:openContent (suffix)");
    // Every node is connected: nothing is drawn floating.
    const targets = new Set(graph.edges.map((e) => e.target));
    expect(graph.nodes.filter((n) => !targets.has(n.id))).toHaveLength(1);
  });

  it("keeps the element collapsible and part of expand-all", () => {
    expect(captions([])).toEqual([]);
    const shape = buildDiagramGraph(alternativesModel, new Set(), null).nodes[0];
    expect(shape.data).toMatchObject({ expandable: true, alternativesCount: 2 });
    expect(collectExpandableElementIds(alternativesModel).has(SHAPE_ID)).toBe(true);
  });
});
