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
import { occursStyle } from "../../lib/cardinality";
import {
  collectElementAssertions,
  countAssertions,
  makeModelResolver,
  type TypeResolver,
} from "../../lib/assertions";
import { effectiveAttributes, effectiveParticle, type ComplexResolver } from "../../lib/effectiveContent";
import { wildcardNamespaceLabel } from "../../lib/attributeGroups";
import type { ElementNodeAttribute } from "./ElementNode";

export const NODE_WIDTH = 220;
export const COMPOSITOR_WIDTH = 70;
export const COMPOSITOR_HEIGHT = 40;

// Pixel budget per node section, measured from the rendered ElementNode in
// Chromium (see the "height budget" test). The layout stacks siblings using
// these numbers, so a budget below the real height overlaps neighbours; if
// you change the CSS in ElementNode.tsx, re-measure and adjust.
const BORDER_H = 2; // 1px top + bottom on the node container
const REPEAT_BORDER_EXTRA = 2; // repeating nodes draw a 2px border (+1px top/bottom)
const HEADER_H = 25; // py-1 + 16px line + 1px border-b
const TYPE_H = 24; // py-1 + 16px line
const SECTION_PAD = 9; // 1px border-t + py-1
const ATTR_ROW_H = 16; // text-[10px] inherits the 16px text-xs line height
const ATTR_ROW_GAP = 2; // space-y-0.5
const DOC_LINE_H = 14; // text-[10px] leading-snug
const EXPAND_HINT_H = 21; // 1px border-t + py-0.5 + 16px line
const MAX_INLINE_ATTRS = 4;
const MAX_DOC_LINES = 2;

// Height of a plain element node (header + type row, nothing else).
export const NODE_HEIGHT = BORDER_H + HEADER_H + TYPE_H;

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
  // Resolves a type's assertions (own + extension/restriction base chain,
  // including simple types) for the ⚖ badge — see lib/assertions.ts.
  assertionResolver: TypeResolver;
  // Resolves a complexType QName against `typeIndex`, for
  // effectiveParticle/effectiveAttributes' base-chain walk (extension content
  // = sequence(base content, own content) — see lib/effectiveContent.ts).
  complexResolver: ComplexResolver;
  // Captions for the particles this module makes up (open content, type
  // alternatives), which have no counterpart in the schema's content model.
  decor: WeakMap<Particle, { caption: string; title: string }>;
}

function nextId(context: BuildContext): string {
  context.idCounter += 1;
  return `node-${context.idCounter}`;
}

function makeComplexResolver(
  typeIndex: Map<string, ComplexType>,
  model: SchemaModel,
): ComplexResolver {
  const resolver: ComplexResolver = (typeRef) => {
    if (!typeRef) return undefined;
    const direct = typeIndex.get(typeRef);
    if (direct) return direct;
    const local = typeRef.includes(":") ? typeRef.split(":").pop()! : typeRef;
    return typeIndex.get(local);
  };
  // For the xs:anyAttribute a type ends up with (effectiveAttributes).
  const groups = new Map(model.attribute_groups.map((g) => [g.name, g]));
  resolver.attributeGroup = (ref) => groups.get(ref.includes(":") ? ref.split(":").pop()! : ref);
  const namespaces = new Map(model.files.map((f) => [f.id, f.target_namespace]));
  resolver.targetNamespace = (ref) => (ref ? namespaces.get(ref.file_id) : undefined);
  return resolver;
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

  // Attributes come from whichever complex type the element resolves to —
  // anonymous inline *or* named (FundsXML's `FXRate type="FXRateType"`, a
  // simpleContent extension carrying fromCcy/toCcy/mulDiv). Only drawing
  // them for inline types silently dropped every named-type attribute.
  const effective = resolvedComplex
    ? effectiveAttributes(resolvedComplex, context.complexResolver)
    : null;
  // An xs:anyAttribute goes last, as one more attribute row: "@* : ##other".
  const attrs: ElementNodeAttribute[] = [
    ...(effective?.attributes ?? []),
    ...(effective?.completeAnyAttribute
      ? [
          {
            id: `anyAttribute:${element.id}`,
            name: "*",
            type_name: wildcardNamespaceLabel(effective.completeAnyAttribute),
          },
        ]
      : []),
  ];
  const docFull = collectDocumentation(element) ?? collectDocumentation(target);
  const docLines = truncateDocLines(docFull);
  // Expanding reveals the effective (base-merged) particle as compositor /
  // child nodes; attributes are already drawn inline on this node. So only a
  // particle makes the node expandable — a `<xs:simpleContent>` extension of
  // xs:string (OeNBCheck's Infos/Info) or an attribute-only type is a leaf.
  const expandable =
    (target.alternatives?.length ?? 0) > 0 ||
    (resolvedComplex != null &&
      effectiveParticle(resolvedComplex, context.complexResolver).particle != null);
  const { optional, repeating } = hostParticle
    ? occursStyle(hostParticle.min_occurs, hostParticle.max_occurs)
    : { optional: false, repeating: false };
  const assertCount = countAssertions(
    collectElementAssertions(target, context.assertionResolver),
  );
  const alternativesCount = target.alternatives?.length ?? 0;
  const idRole = target.id_role ?? null;
  const identityConstraints = target.identity_constraints ?? [];
  const identityConstraintCount = identityConstraints.length;
  const identityConstraintTitle = identityConstraintCount
    ? identityConstraints.map((c) => `${c.kind} ${c.name}`).join(", ")
    : null;

  // Row counts that actually render in ElementNode.tsx.
  const attrRows =
    Math.min(attrs.length, MAX_INLINE_ATTRS) + (attrs.length > MAX_INLINE_ATTRS ? 1 : 0);

  let height = NODE_HEIGHT;
  if (repeating) height += REPEAT_BORDER_EXTRA;
  if (attrRows) {
    height += SECTION_PAD + attrRows * ATTR_ROW_H + (attrRows - 1) * ATTR_ROW_GAP;
  }
  if (docLines.length) height += SECTION_PAD + docLines.length * DOC_LINE_H;
  if (expandable) height += EXPAND_HINT_H;

  const data = {
    schemaId: element.id,
    kind: "element",
    label: element.name ?? element.ref ?? "?",
    type: target.type_name,
    occurs: hostParticle ? formatOccurs(hostParticle.min_occurs, hostParticle.max_occurs) : null,
    optional,
    repeating,
    expandable,
    expanded: context.expandedIds.has(element.id),
    selected: context.selectedId === element.id,
    attributes: attrs,
    documentationLines: docLines,
    documentationFull: docFull,
    assertCount,
    alternativesCount,
    idRole,
    identityConstraintCount,
    identityConstraintTitle,
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
  // Cardinality of the particle (drives the border style) plus optional
  // XSD 1.1 cues that decorate the compositor.
  extras: {
    optional?: boolean;
    repeating?: boolean;
    openContentMode?: "interleave" | "suffix" | "none";
    caption?: string;
    title?: string;
  } = {},
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

function syntheticParticle(kind: Particle["kind"], overrides: Partial<Particle> = {}): Particle {
  return {
    kind,
    min_occurs: 1,
    max_occurs: 1,
    element: null,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
    ...overrides,
  };
}

// The content of a complex type as the diagram draws it: the effective
// particle, plus one more "any" leaf for XSD 1.1 open content.
function typeParticle(complex: ComplexType, context: BuildContext): Particle | null {
  const particle = effectiveParticle(complex, context.complexResolver).particle;
  const open = complex.open_content;
  if (!particle || !open || open.mode === "none" || !open.wildcard) return particle;
  const namespaces = wildcardNamespaceLabel(open.wildcard);
  const leaf = syntheticParticle("any", {
    min_occurs: 0,
    max_occurs: "unbounded",
    wildcard_namespace: open.wildcard.namespace,
    wildcard_process_contents: open.wildcard.process_contents,
  });
  context.decor.set(leaf, {
    caption: "open",
    title:
      `xs:openContent (${open.mode}) — any element from: ${namespaces}, ` +
      (open.mode === "suffix" ? "after the declared content" : "anywhere between the declared content"),
  });
  // Beside the content model, not inside it: a choice must not gain a branch.
  return particle.kind === "sequence" && particle.min_occurs === 1 && particle.max_occurs === 1
    ? { ...particle, children: [...particle.children, leaf] }
    : syntheticParticle("sequence", { children: [particle, leaf] });
}

function shortName(qname: string): string {
  return qname.includes(":") ? qname.split(":").pop()! : qname;
}

// XSD 1.1 xs:alternative: the element's type depends on its attributes. Drawn
// as a choice between the types, each branch holding that type's content; the
// declared type is the last branch unless an alternative without a test
// already says what applies otherwise.
function alternativesParticle(
  target: ElementDecl,
  declared: ComplexType | undefined,
  context: BuildContext,
): Particle {
  const branch = (
    caption: string,
    title: string,
    complex: ComplexType | undefined | null,
  ): Particle => {
    const content = complex ? typeParticle(complex, context) : null;
    const particle = syntheticParticle("sequence", { children: content ? [content] : [] });
    context.decor.set(particle, { caption, title });
    return particle;
  };
  const alternatives = target.alternatives ?? [];
  const branches = alternatives.map((alternative) => {
    const complex =
      alternative.type_inline_complex ?? resolveComplex(alternative.type_name, context);
    const name = alternative.type_name ? shortName(alternative.type_name) : "inline";
    return branch(
      name,
      alternative.test == null
        ? `xs:alternative — otherwise: ${alternative.type_name ?? "inline type"}`
        : `xs:alternative — if ${alternative.test}: ${alternative.type_name ?? "inline type"}`,
      complex,
    );
  });
  if (!alternatives.some((a) => a.test == null)) {
    branches.push(
      branch(
        target.type_name ? shortName(target.type_name) : "declared",
        `otherwise the declared type${target.type_name ? `: ${target.type_name}` : ""}`,
        declared,
      ),
    );
  }
  const root = syntheticParticle("choice", { children: branches });
  context.decor.set(root, {
    caption: "type?",
    title: "XSD 1.1 type alternatives — which type applies depends on the element's attributes",
  });
  return root;
}

function contentParticle(element: ElementDecl, context: BuildContext): Particle | null {
  const target = resolveRefTarget(element, context);
  const complex = target.type_inline_complex ?? resolveComplex(target.type_name, context);
  if (target.alternatives?.length) return alternativesParticle(target, complex, context);
  return complex ? typeParticle(complex, context) : null;
}

function getExpandedParticle(
  element: ElementDecl,
  context: BuildContext,
): Particle | null {
  if (!context.expandedIds.has(element.id)) return null;
  return contentParticle(element, context);
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

  // Everything the recursion pushes from here on is this element's subtree,
  // so we can translate it as a block once we know where the element lands.
  const subtreeStart = context.nodes.length;

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

  // Parent element sits on the same midline as the compositor. When the
  // element is taller than its whole expanded subtree — GLEIF's `Extension`,
  // a documented element whose type is just `<xs:sequence><xs:any/></…>` —
  // that midline would lift it above `topY` and straight over the sibling
  // placed before it. Callers stack siblings by advancing past `span.bottomY`,
  // so a subtree must never draw above the `topY` it was handed: push the
  // children down instead, keeping element and compositor on one midline.
  const overshoot = topY + display.height / 2 - particleResult.span.centerY;
  if (overshoot > 0) {
    for (let i = subtreeStart; i < context.nodes.length; i++) {
      const node = context.nodes[i];
      node.position = { x: node.position.x, y: node.position.y + overshoot };
    }
    particleResult.span = {
      topY: particleResult.span.topY + overshoot,
      bottomY: particleResult.span.bottomY + overshoot,
      centerY: particleResult.span.centerY + overshoot,
    };
  }

  const center = particleResult.span.centerY;
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
    addCompositorNode(
      flowId,
      "any",
      "any",
      compositorX,
      topY,
      context,
      { ...occursStyle(particle.min_occurs, particle.max_occurs), ...context.decor.get(particle) },
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

  if (particle.kind === "group-ref") {
    const flowId = nextId(context);
    addCompositorNode(
      flowId,
      "group-ref",
      particle.group_ref ?? "group",
      compositorX,
      topY,
      context,
      occursStyle(particle.min_occurs, particle.max_occurs),
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
    { ...occursStyle(particle.min_occurs, particle.max_occurs), ...context.decor.get(particle) },
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
  const typeIndex = buildTypeIndex(model);
  const context: BuildContext = {
    model,
    expandedIds,
    selectedId,
    nodes: [],
    edges: [],
    idCounter: 0,
    typeIndex,
    elementIndex: buildElementIndex(model),
    pathIds: new Set(),
    assertionResolver: makeModelResolver(model),
    complexResolver: makeComplexResolver(typeIndex, model),
    decor: new WeakMap(),
  };

  let nextTopY = 0;
  for (const element of computeRootElements(model)) {
    const { span } = placeElement(element, 0, nextTopY, null, context);
    nextTopY = span.bottomY + TREE_GAP;
  }

  return { nodes: context.nodes, edges: context.edges };
}
