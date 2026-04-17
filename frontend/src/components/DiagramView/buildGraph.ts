// Builds a React-Flow graph from the schema model.
//
// Strategy: top-level global elements are root nodes. When expanded, a node
// unfolds its particle children. A lightweight layered layout places each
// tree vertically, with children to the right.

import type { Edge, Node } from "@xyflow/react";
import type {
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../../types/schema";

const NODE_WIDTH = 220;
const NODE_HEIGHT = 56;
const X_GAP = 100;
const Y_GAP = 24;

interface BuildContext {
  model: SchemaModel;
  expandedIds: Set<string>;
  selectedId: string | null;
  nodes: Node[];
  edges: Edge[];
  y: number;
  idCounter: number;
  typeIndex: Map<string, ComplexType>;
}

function uniqueId(context: BuildContext): string {
  context.idCounter += 1;
  return `node-${context.idCounter}`;
}

function buildTypeIndex(model: SchemaModel): Map<string, ComplexType> {
  const index = new Map<string, ComplexType>();
  for (const complex of model.complex_types) {
    if (complex.name) {
      index.set(complex.name, complex);
      // Also register the namespaced expansion so "tns:Foo" lookups work.
      if (model.target_namespace) {
        index.set(`{${model.target_namespace}}${complex.name}`, complex);
      }
    }
  }
  return index;
}

function resolveComplex(
  typeRef: string | null | undefined,
  context: BuildContext,
): ComplexType | undefined {
  if (!typeRef) return undefined;
  const direct = context.typeIndex.get(typeRef);
  if (direct) return direct;
  const local = typeRef.includes(":") ? typeRef.split(":").pop()! : typeRef;
  return context.typeIndex.get(local);
}

function addElementNode(
  element: ElementDecl,
  x: number,
  y: number,
  parentId: string | null,
  particle: Particle | null,
  context: BuildContext,
): string {
  const id = uniqueId(context);
  const expandable =
    element.type_inline_complex != null || resolveComplex(element.type_name, context) != null;
  context.nodes.push({
    id,
    position: { x, y },
    data: {
      schemaId: element.id,
      kind: "element",
      label: element.name ?? element.ref ?? "?",
      type: element.type_name,
      occurs: particle ? formatOccurs(particle.min_occurs, particle.max_occurs) : null,
      expandable,
      expanded: context.expandedIds.has(element.id),
      selected: context.selectedId === element.id,
      attributes: element.type_inline_complex?.attributes ?? [],
    },
    type: "element",
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  });
  if (parentId) {
    context.edges.push({
      id: `${parentId}-${id}`,
      source: parentId,
      target: id,
      type: "smoothstep",
    });
  }
  return id;
}

function addCompositorNode(
  kind: "sequence" | "choice" | "all" | "any" | "group-ref",
  label: string,
  x: number,
  y: number,
  parentId: string | null,
  context: BuildContext,
): string {
  const id = uniqueId(context);
  context.nodes.push({
    id,
    position: { x, y },
    data: { kind, label },
    type: "compositor",
    width: 70,
    height: 40,
  });
  if (parentId) {
    context.edges.push({
      id: `${parentId}-${id}`,
      source: parentId,
      target: id,
      type: "smoothstep",
    });
  }
  return id;
}

function formatOccurs(min: number, max: number | "unbounded"): string | null {
  if (min === 1 && max === 1) return null;
  return `[${min}..${max === "unbounded" ? "∞" : max}]`;
}

function expandParticle(
  particle: Particle,
  x: number,
  parentFlowId: string,
  context: BuildContext,
): number {
  // Returns the max Y coordinate used.
  let localY = context.y;
  if (particle.kind === "element" && particle.element) {
    const element = particle.element;
    const elementId = addElementNode(
      element,
      x,
      context.y,
      parentFlowId,
      particle,
      context,
    );
    context.y += NODE_HEIGHT + Y_GAP;
    localY = context.y;
    if (context.expandedIds.has(element.id)) {
      const complex = element.type_inline_complex ?? resolveComplex(element.type_name, context);
      if (complex?.particle) {
        localY = expandParticle(complex.particle, x + NODE_WIDTH + X_GAP, elementId, context);
      }
    }
  } else if (particle.kind === "group-ref") {
    addCompositorNode(
      "group-ref",
      particle.group_ref ?? "group",
      x,
      context.y,
      parentFlowId,
      context,
    );
    context.y += NODE_HEIGHT + Y_GAP;
    localY = context.y;
  } else if (particle.kind === "any") {
    addCompositorNode("any", "any", x, context.y, parentFlowId, context);
    context.y += NODE_HEIGHT + Y_GAP;
    localY = context.y;
  } else {
    // sequence / choice / all → add a compositor and expand children to its right
    const compositorId = addCompositorNode(
      particle.kind as "sequence" | "choice" | "all",
      particle.kind,
      x,
      context.y,
      parentFlowId,
      context,
    );
    context.y += NODE_HEIGHT + Y_GAP;
    const childrenX = x + NODE_WIDTH + X_GAP;
    let maxY = context.y;
    for (const child of particle.children) {
      const used = expandParticle(child, childrenX, compositorId, context);
      maxY = Math.max(maxY, used);
    }
    localY = maxY;
  }
  return Math.max(localY, context.y);
}

export function buildDiagramGraph(
  model: SchemaModel,
  expandedIds: Set<string>,
  selectedId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const context: BuildContext = {
    model,
    expandedIds,
    selectedId,
    nodes: [],
    edges: [],
    y: 0,
    idCounter: 0,
    typeIndex: buildTypeIndex(model),
  };

  for (const element of model.elements) {
    const elementId = addElementNode(element, 0, context.y, null, null, context);
    context.y += NODE_HEIGHT + Y_GAP;
    if (expandedIds.has(element.id)) {
      const complex = element.type_inline_complex ?? resolveComplex(element.type_name, context);
      if (complex?.particle) {
        expandParticle(complex.particle, NODE_WIDTH + X_GAP, elementId, context);
      }
    }
    context.y += Y_GAP * 2; // extra space between top-level trees
  }

  return { nodes: context.nodes, edges: context.edges };
}
