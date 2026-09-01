// Builds a React-Flow graph from the schema model.
//
// Layout: classic XSD-diagram style (à la XMLSpy / Oxygen).
// A parent element and its compositor sit on the same horizontal baseline,
// with the compositor's children stacked vertically to its right and the
// compositor vertically centered on the children's span.
//
//   [Parent] ── [Seq] ── Child 1
//                    ├── Child 2   ← compositor on Y-midpoint of children
//                    └── Child 3
//
// Algorithm: bottom-up recursion. Children are placed first; their combined
// vertical span determines the Y-center on which the parent/compositor are
// then aligned.

import type { Edge, Node } from "@xyflow/react";
import type {
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../../types/schema";
import { computeRootElements } from "../../lib/rootElements";

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 56; // base height for a plain element node
export const COMPOSITOR_WIDTH = 70;
export const COMPOSITOR_HEIGHT = 40;

// Pixel budget per body row. Matches the `text-[11px]` / `text-[10px]`
// line heights in ElementNode.tsx; if you change the CSS, adjust these.
const HEADER_H = 24;
const TYPE_H = 20;
const ROW_H = 14;
const DOC_LINE_H = 16;
const SECTION_PAD = 4;
const EXPAND_HINT_H = 14;
const MAX_INLINE_ATTRS = 4;
const MAX_DOC_LINES = 2;

const X_GAP = 60;
const Y_GAP = 24;
const TREE_GAP = Y_GAP * 2;

interface Span {
  topY: number;
  bottomY: number;
  centerY: number;
}

interface BuildContext {
  model: SchemaModel;
  expandedIds: Set<string>;
  selectedId: string | null;
  nodes: Node[];
  edges: Edge[];
  idCounter: number;
  typeIndex: Map<string, ComplexType>;
  // Global element declarations by id, so an `<xs:element ref="…">` particle
  // can be resolved to the declaration that actually carries its content.
  elementIndex: Map<string, ElementDecl>;
  // Ids of the elements on the current root→node path. A recursive schema
  // (a type whose content refs the element it defines) would otherwise expand
  // forever, since every repetition of the ref carries the same id.
  pathIds: Set<string>;
}

function nextId(context: BuildContext): string {
  context.idCounter += 1;
  return `node-${context.idCounter}`;
}

function buildTypeIndex(model: SchemaModel): Map<string, ComplexType> {
  const index = new Map<string, ComplexType>();
  for (const complex of model.complex_types) {
    if (!complex.name) continue;
    index.set(complex.name, complex);
    if (model.target_namespace) {
      index.set(`{${model.target_namespace}}${complex.name}`, complex);
    }
  }
  return index;
}

function buildElementIndex(model: SchemaModel): Map<string, ElementDecl> {
  const index = new Map<string, ElementDecl>();
  for (const element of model.elements) {
    index.set(element.id, element);
  }
  return index;
}

// An `<xs:element ref="…">` particle holds no type of its own — everything the
// node renders (type, children, documentation) lives on the referenced global
// declaration, which for an imported namespace sits in another file.
function resolveRefTarget(
  element: ElementDecl,
  context: BuildContext,
): ElementDecl {
  if (!element.ref || !element.ref_id) return element;
  return context.elementIndex.get(element.ref_id) ?? element;
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

function collectDocumentation(element: ElementDecl): string | null {
  const docs = element.annotation?.documentation ?? [];
  for (const frag of docs) {
    const trimmed = frag.text?.trim();
    if (trimmed) return trimmed;
  }
  return null;
}

function formatOccurs(min: number, max: number | "unbounded"): string | null {
  if (min === 1 && max === 1) return null;
  return `[${min}..${max === "unbounded" ? "∞" : max}]`;
}

interface ElementDisplay {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>;
  height: number;
}

function truncateDocLines(doc: string | null): string[] {
  if (!doc) return [];
  const lines = doc.split(/\r?\n/).filter((l) => l.trim().length > 0);
  return lines.slice(0, MAX_DOC_LINES);
}

function computeElementDisplay(
  element: ElementDecl,
  hostParticle: Particle | null,
  context: BuildContext,
): ElementDisplay {
  const target = resolveRefTarget(element, context);
  const inlineComplex = target.type_inline_complex;
  const namedComplex = !inlineComplex ? resolveComplex(target.type_name, context) : undefined;
  const resolvedComplex = inlineComplex ?? namedComplex ?? null;

  const attrs = inlineComplex?.attributes ?? [];
  const docFull = collectDocumentation(element) ?? collectDocumentation(target);
  const docLines = truncateDocLines(docFull);
  const expandable = resolvedComplex != null;
  const assertCount = resolvedComplex?.assertions?.length ?? 0;
  const alternativesCount = element.alternatives?.length ?? 0;

  // Row counts that actually render in ElementNode.tsx.
  const attrRows =
    Math.min(attrs.length, MAX_INLINE_ATTRS) + (attrs.length > MAX_INLINE_ATTRS ? 1 : 0);

  let height = HEADER_H + TYPE_H;
  if (attrRows) height += SECTION_PAD + attrRows * ROW_H;
  if (docLines.length) height += SECTION_PAD + docLines.length * DOC_LINE_H;
  if (expandable) height += EXPAND_HINT_H;
  // Ensure the expanded-case header/title always has room.
  height = Math.max(height, NODE_HEIGHT);

  const data = {
    schemaId: element.id,
    kind: "element",
    label: element.name ?? element.ref ?? "?",
    type: target.type_name,
    occurs: hostParticle ? formatOccurs(hostParticle.min_occurs, hostParticle.max_occurs) : null,
    expandable,
    expanded: context.expandedIds.has(element.id),
    selected: context.selectedId === element.id,
    attributes: attrs,
    documentationLines: docLines,
    documentationFull: docFull,
    assertCount,
    alternativesCount,
  };
  return { data, height };
}

function addElementNode(
  id: string,
  display: ElementDisplay,
  x: number,
  y: number,
  context: BuildContext,
): void {
  context.nodes.push({
    id,
    position: { x, y },
    data: display.data,
    type: "element",
    width: NODE_WIDTH,
    height: display.height,
  });
}

function addCompositorNode(
  id: string,
  kind: "sequence" | "choice" | "all" | "any" | "group-ref",
  label: string,
  x: number,
  y: number,
  context: BuildContext,
  // Optional XSD 1.1 cues that decorate the compositor.
  extras: { openContentMode?: "interleave" | "suffix" | "none" } = {},
): void {
  context.nodes.push({
    id,
    position: { x, y },
    data: { kind, label, ...extras },
    type: "compositor",
    width: COMPOSITOR_WIDTH,
    height: COMPOSITOR_HEIGHT,
  });
}

function addEdge(context: BuildContext, source: string, target: string): void {
  context.edges.push({
    id: `${source}-${target}`,
    source,
    target,
    type: "smoothstep",
  });
}

function getExpandedParticle(
  element: ElementDecl,
  context: BuildContext,
): Particle | null {
  if (!context.expandedIds.has(element.id)) return null;
  const target = resolveRefTarget(element, context);
  const complex = target.type_inline_complex ?? resolveComplex(target.type_name, context);
  return complex?.particle ?? null;
}

function getOpenContentMode(
  element: ElementDecl,
  context: BuildContext,
): "interleave" | "suffix" | "none" | null {
  const target = resolveRefTarget(element, context);
  const complex = target.type_inline_complex ?? resolveComplex(target.type_name, context);
  return complex?.open_content?.mode ?? null;
}

// Places an element, recursing into its content model if expanded.
// Returns the vertical span consumed by the entire sub-tree.
function placeElement(
  element: ElementDecl,
  x: number,
  topY: number,
  hostParticle: Particle | null,
  context: BuildContext,
): { flowId: string; span: Span } {
  const display = computeElementDisplay(element, hostParticle, context);
  const expandedParticle = context.pathIds.has(element.id)
    ? null
    : getExpandedParticle(element, context);

  if (!expandedParticle) {
    const flowId = nextId(context);
    addElementNode(flowId, display, x, topY, context);
    return {
      flowId,
      span: {
        topY,
        bottomY: topY + display.height,
        centerY: topY + display.height / 2,
      },
    };
  }

  // Expanded: lay out the particle subtree to the right, then center the
  // element (and the compositor) vertically on the span of the children.
  const compositorX = x + NODE_WIDTH + X_GAP;
  const childrenX = compositorX + COMPOSITOR_WIDTH + X_GAP;

  const elementFlowId = nextId(context);

  context.pathIds.add(element.id);
  const particleResult = placeParticle(
    expandedParticle,
    compositorX,
    childrenX,
    topY,
    context,
  );
  context.pathIds.delete(element.id);

  // The root compositor of an expanded element is the visual host for any
  // open-content semantics declared on that element's complex type. Tag it
  // so CompositorNode can render the dashed border + corner glyph.
  const openContentMode = getOpenContentMode(element, context);
  if (openContentMode) {
    const rootNode = context.nodes.find((n) => n.id === particleResult.rootFlowId);
    if (rootNode && rootNode.type === "compositor") {
      // Mutate the data we just pushed; safe since no consumer has read it.
      (rootNode.data as Record<string, unknown>).openContentMode = openContentMode;
    }
  }

  const center = particleResult.span.centerY;

  // Parent element sits on the same midline as the compositor.
  const elementTopY = center - display.height / 2;
  addElementNode(elementFlowId, display, x, elementTopY, context);
  addEdge(context, elementFlowId, particleResult.rootFlowId);

  const finalSpan: Span = {
    topY: Math.min(particleResult.span.topY, elementTopY),
    bottomY: Math.max(particleResult.span.bottomY, elementTopY + display.height),
    centerY: center,
  };
  return { flowId: elementFlowId, span: finalSpan };
}

// Places a particle. For sequence/choice/all: creates a compositor node
// plus every child; for element-particles: delegates to placeElement;
// for any/group-ref: single leaf node.
// Returns a flowId representing the root node the caller should connect to,
// plus the span consumed.
function placeParticle(
  particle: Particle,
  compositorX: number,
  childrenX: number,
  topY: number,
  context: BuildContext,
): { rootFlowId: string; span: Span } {
  if (particle.kind === "element" && particle.element) {
    const { flowId, span } = placeElement(
      particle.element,
      compositorX,
      topY,
      particle,
      context,
    );
    return { rootFlowId: flowId, span };
  }

  if (particle.kind === "any") {
    const flowId = nextId(context);
    addCompositorNode(flowId, "any", "any", compositorX, topY, context);
    return {
      rootFlowId: flowId,
      span: {
        topY,
        bottomY: topY + COMPOSITOR_HEIGHT,
        centerY: topY + COMPOSITOR_HEIGHT / 2,
      },
    };
  }

  if (particle.kind === "group-ref") {
    const flowId = nextId(context);
    addCompositorNode(
      flowId,
      "group-ref",
      particle.group_ref ?? "group",
      compositorX,
      topY,
      context,
    );
    return {
      rootFlowId: flowId,
      span: {
        topY,
        bottomY: topY + COMPOSITOR_HEIGHT,
        centerY: topY + COMPOSITOR_HEIGHT / 2,
      },
    };
  }

  // sequence | choice | all — stack children vertically to the right, then
  // center the compositor on their combined span.
  const compositorId = nextId(context);

  const grandchildX = childrenX + NODE_WIDTH + X_GAP + COMPOSITOR_WIDTH + X_GAP;
  let cursorY = topY;
  const childResults: { rootFlowId: string; span: Span }[] = [];

  for (const child of particle.children) {
    const result = placeParticle(child, childrenX, grandchildX, cursorY, context);
    childResults.push(result);
    cursorY = result.span.bottomY + Y_GAP;
  }

  let childrenSpan: Span;
  if (childResults.length === 0) {
    childrenSpan = {
      topY,
      bottomY: topY + COMPOSITOR_HEIGHT,
      centerY: topY + COMPOSITOR_HEIGHT / 2,
    };
  } else {
    const first = childResults[0].span.topY;
    const last = childResults[childResults.length - 1].span.bottomY;
    childrenSpan = { topY: first, bottomY: last, centerY: (first + last) / 2 };
  }

  const compositorY = childrenSpan.centerY - COMPOSITOR_HEIGHT / 2;
  // XSD 1.1 lifts the maxOccurs<=1 / no-wildcard restrictions on xs:all.
  // Tag the label with "+" when either relaxation is exercised.
  const isAllPlus =
    particle.kind === "all" &&
    (particle.max_occurs === "unbounded" ||
      (typeof particle.max_occurs === "number" && particle.max_occurs > 1) ||
      particle.children.some((c) => c.kind === "any"));
  addCompositorNode(
    compositorId,
    particle.kind as "sequence" | "choice" | "all",
    isAllPlus ? "all+" : particle.kind,
    compositorX,
    compositorY,
    context,
  );
  for (const child of childResults) {
    addEdge(context, compositorId, child.rootFlowId);
  }

  return {
    rootFlowId: compositorId,
    span: {
      topY: Math.min(childrenSpan.topY, compositorY),
      bottomY: Math.max(childrenSpan.bottomY, compositorY + COMPOSITOR_HEIGHT),
      centerY: childrenSpan.centerY,
    },
  };
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
    idCounter: 0,
    typeIndex: buildTypeIndex(model),
    elementIndex: buildElementIndex(model),
    pathIds: new Set(),
  };

  let nextTopY = 0;
  for (const element of computeRootElements(model)) {
    const { span } = placeElement(element, 0, nextTopY, null, context);
    nextTopY = span.bottomY + TREE_GAP;
  }

  return { nodes: context.nodes, edges: context.edges };
}
