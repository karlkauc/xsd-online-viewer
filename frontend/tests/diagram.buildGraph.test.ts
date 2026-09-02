import { describe, expect, it } from "vitest";
import type { Node } from "@xyflow/react";
import type { SchemaModel } from "../src/types/schema";
import {
  buildDiagramGraph,
  COMPOSITOR_HEIGHT,
} from "../src/components/DiagramView/buildGraph";
import { smallModel } from "./fixtures/smallModel";
import { refModel, DOCUMENT_ID, SIGNATURE_REF_ID } from "./fixtures/refModel";

const PERSON_ID = "element:{http://example.com/simple}Person";
const ADDRESS_ID = "element:{http://example.com/simple}PersonType/Address";

function findBySchemaId(nodes: Node[], schemaId: string): Node | undefined {
  return nodes.find(
    (n) => (n.data as { schemaId?: string } | undefined)?.schemaId === schemaId,
  );
}

function compositorNodes(nodes: Node[]): Node[] {
  return nodes.filter((n) => n.type === "compositor");
}

function nodeHeight(node: Node): number {
  const h = node.height;
  if (typeof h !== "number") throw new Error(`node ${node.id} missing height`);
  return h;
}

function centerY(node: Node, height: number): number {
  return node.position.y + height / 2;
}

describe("buildDiagramGraph layout", () => {
  it("produces a single element node when nothing is expanded", () => {
    const { nodes } = buildDiagramGraph(smallModel, new Set(), null);
    expect(nodes).toHaveLength(1);
    expect(nodes[0].position).toEqual({ x: 0, y: 0 });
    expect(compositorNodes(nodes)).toHaveLength(0);
  });

  it("centers parent + compositor on the midpoint of their children", () => {
    const expanded = new Set([PERSON_ID]);
    const { nodes, edges } = buildDiagramGraph(smallModel, expanded, null);

    // 6 children (FirstName/LastName/Address/Age/Color/Email) + 1 compositor + 1 parent.
    expect(nodes).toHaveLength(8);
    const compositors = compositorNodes(nodes);
    expect(compositors).toHaveLength(1);
    expect((compositors[0].data as { kind: string }).kind).toBe("sequence");

    const childNames = ["FirstName", "LastName", "Address", "Age", "Color", "Email"];
    const childNodes = childNames.map((name) => {
      const hit = nodes.find(
        (n) => n.type === "element" && (n.data as { label: string }).label === name,
      );
      if (!hit) throw new Error(`child ${name} missing`);
      return hit;
    });
    const childXs = new Set(childNodes.map((n) => n.position.x));
    expect(childXs.size).toBe(1);

    // Children stack in declaration order, strictly increasing Y.
    for (let i = 1; i < childNodes.length; i++) {
      expect(childNodes[i].position.y).toBeGreaterThan(childNodes[i - 1].position.y);
    }

    // Compositor sits on the Y-midpoint of the children span.
    const first = childNodes[0];
    const last = childNodes[childNodes.length - 1];
    const expectedCenter = (first.position.y + last.position.y + nodeHeight(last)) / 2;
    const compositorCenter = centerY(compositors[0], COMPOSITOR_HEIGHT);
    expect(Math.abs(compositorCenter - expectedCenter)).toBeLessThanOrEqual(1);

    // Parent element sits on the same midline as the compositor.
    const parent = findBySchemaId(nodes, PERSON_ID);
    expect(parent).toBeDefined();
    const parentCenter = centerY(parent!, nodeHeight(parent!));
    expect(Math.abs(parentCenter - compositorCenter)).toBeLessThanOrEqual(1);

    // Spatial ordering: parent → compositor → children.
    expect(compositors[0].position.x).toBeGreaterThan(parent!.position.x);
    expect(childNodes[0].position.x).toBeGreaterThan(compositors[0].position.x);

    // Edge structure: parent → compositor, then compositor → each child.
    expect(edges).toHaveLength(1 + childNodes.length);
    const compositorOut = edges.filter((e) => e.source === compositors[0].id);
    expect(compositorOut).toHaveLength(childNodes.length);
  });

  it("re-centers when a nested element is also expanded", () => {
    const expanded = new Set([PERSON_ID, ADDRESS_ID]);
    const { nodes } = buildDiagramGraph(smallModel, expanded, null);

    const compositors = compositorNodes(nodes);
    expect(compositors).toHaveLength(2);

    const address = findBySchemaId(nodes, ADDRESS_ID);
    expect(address).toBeDefined();

    const street = nodes.find(
      (n) => n.type === "element" && (n.data as { label: string }).label === "Street",
    )!;
    const city = nodes.find(
      (n) => n.type === "element" && (n.data as { label: string }).label === "City",
    )!;

    const innerCompositor = compositors.find(
      (c) => c.position.x > address!.position.x,
    );
    expect(innerCompositor).toBeDefined();
    const innerCenter = centerY(innerCompositor!, COMPOSITOR_HEIGHT);
    const addressCenter = centerY(address!, nodeHeight(address!));
    expect(Math.abs(addressCenter - innerCenter)).toBeLessThanOrEqual(1);

    const expected = (street.position.y + city.position.y + nodeHeight(city)) / 2;
    expect(Math.abs(innerCenter - expected)).toBeLessThanOrEqual(1);
  });
});

describe("buildDiagramGraph node metadata", () => {
  it("attaches the first documentation fragment to the element data", () => {
    const { nodes } = buildDiagramGraph(smallModel, new Set(), null);
    const person = findBySchemaId(nodes, PERSON_ID);
    expect(person).toBeDefined();
    const data = person!.data as {
      documentationLines?: string[];
      documentationFull?: string | null;
    };
    expect(data.documentationFull).toBe("Represents a person.");
    expect(data.documentationLines).toEqual(["Represents a person."]);
  });

  it("grows node height when documentation is present", () => {
    const { nodes } = buildDiagramGraph(smallModel, new Set([PERSON_ID]), null);
    const firstName = nodes.find(
      (n) => n.type === "element" && (n.data as { label: string }).label === "FirstName",
    )!;
    const person = findBySchemaId(nodes, PERSON_ID)!;
    // Person carries a documentation line; FirstName has none. Person must be taller.
    expect(nodeHeight(person)).toBeGreaterThan(nodeHeight(firstName));
  });
});

describe("buildDiagramGraph height budget", () => {
  // Pixel heights measured from the rendered ElementNode in Chromium
  // (container border 2, header 25, type row 24, attribute block
  // 9 + 16/row + 2/gap, documentation block 9 + 14/line, expand hint 21).
  // A budget below the rendered height stacks siblings into each other.
  function attr(name: string) {
    return {
      id: `attribute:${name}`,
      name,
      qname: null,
      ref: null,
      type_name: "xs:string",
      type_inline: null,
      use: "optional" as const,
      default: null,
      fixed: null,
      form: null,
      target_namespace: null,
      is_global: false,
      annotation: null,
      source_ref: null,
    };
  }
  function docs(text: string) {
    return { documentation: [{ lang: null, text, source: "documentation" as const }], appinfo: [], comments: [] };
  }
  function heightOf(model: SchemaModel, label: string): number {
    const { nodes } = buildDiagramGraph(model, new Set([PERSON_ID]), null);
    const node = nodes.find(
      (n) => n.type === "element" && (n.data as { label: string }).label === label,
    );
    if (!node) throw new Error(`node ${label} missing`);
    return nodeHeight(node);
  }

  it("matches the rendered height of every node section", () => {
    const model = structuredClone(smallModel) as SchemaModel;
    const children = model.complex_types[0].particle!.children;
    const firstName = children[0].element!;
    firstName.annotation = docs("Line one\nLine two");
    const address = children[2].element!;
    address.type_inline_complex!.attributes = ["a", "b", "c", "d", "e"].map(attr);
    address.annotation = docs("Line one\nLine two\nLine three");

    expect(heightOf(model, "LastName")).toBe(51); // plain leaf
    expect(heightOf(model, "Person")).toBe(95); // one doc line + expand hint
    expect(heightOf(model, "FirstName")).toBe(88); // two doc lines
    expect(heightOf(model, "Address")).toBe(206); // 4 attrs + "more" row, 2 doc lines, hint
    expect(heightOf(smallModel, "Address")).toBe(72); // expand hint only
  });
});

describe("buildDiagramGraph element references", () => {
  it("expands a ref into the referenced global declaration", () => {
    const collapsed = buildDiagramGraph(refModel, new Set([DOCUMENT_ID]), null);
    const signature = findBySchemaId(collapsed.nodes, SIGNATURE_REF_ID);
    expect(signature).toBeDefined();
    const data = signature!.data as { expandable: boolean; type: string | null };
    expect(data.expandable).toBe(true);
    expect(data.type).toBe("ds:SignatureType");

    const expanded = buildDiagramGraph(
      refModel,
      new Set([DOCUMENT_ID, SIGNATURE_REF_ID]),
      null,
    );
    const signedInfo = expanded.nodes.find(
      (n) => n.type === "element" && (n.data as { label: string }).label === "ds:SignedInfo",
    );
    expect(signedInfo).toBeDefined();
  });
});

describe("buildDiagramGraph reference cycles", () => {
  it("stops instead of recursing when a ref points back at an ancestor", () => {
    // SignatureType gains a ref back to ds:Signature — the shape every
    // recursive schema has (a node type containing a ref to its own element).
    const cyclic = structuredClone(refModel) as SchemaModel;
    const signatureType = cyclic.complex_types[0];
    signatureType.particle!.children.push({
      kind: "element",
      min_occurs: 0,
      max_occurs: "unbounded",
      element: {
        ...cyclic.elements[0].type_inline_complex!.particle!.children[1].element!,
      },
      group_ref: null,
      group_inline: null,
      children: [],
      wildcard_namespace: null,
      wildcard_process_contents: null,
      annotation: null,
    });

    const { nodes } = buildDiagramGraph(
      cyclic,
      new Set([DOCUMENT_ID, SIGNATURE_REF_ID]),
      null,
    );
    expect(nodes.length).toBeLessThan(20);
  });
});
