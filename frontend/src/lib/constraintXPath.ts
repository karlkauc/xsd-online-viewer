// Resolves the raw XPath 1.0 ``selector``/``fields`` strings carried by an
// identity constraint (``xs:key``/``xs:keyref``/``xs:unique``) into a chain of
// tokens, some of which point at a concrete element/attribute declaration in
// this schema. Pure — no store access; Task 6 renders the tokens as clickable
// step chains.
//
// Grammar supported (XSD §3.11.6 subset):
//   Paths  ::= Path ('|' Path)*
//   Path   ::= ('.//')? Step ('/' Step)*
//   Step   ::= '.' | ('child::')? NameTest | '@' NCName | 'attribute::' NCName
//   NameTest ::= QName | '*' | NCName ':*'
// Namespace prefixes are never validated against `xmlns` bindings — every
// name test matches on local name only, per the task brief.
//
// Resolution walks the *schema* (declarations), not an instance document: at
// each step we ask "what could this name mean from here", using the same
// content-model flattening rules the rest of the viewer already applies
// (extension base chains, group refs, element refs). A step that doesn't
// match anything leaves that token — and every token after it — with a null
// target; the caller renders those as plain, unclickable text.

import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  Group,
  IdentityConstraint,
  NodeIndexEntry,
  Particle,
  SchemaNodeKind,
} from "../types/schema";
import { resolveElementRef, resolveReference } from "./indexSchema";
import { collectFromGroup, type ResolvedAttribute } from "./attributeGroups";

// BFS depth cap for the `.//` descendant search, and a general safety net
// against recursive schemas (an element whose type (transitively) contains
// itself) — see findDescendantElement.
const MAX_DESCENDANT_DEPTH = 8;

export interface ResolveContext {
  index: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
}

export interface PathToken {
  /** Verbatim source text — concatenating every token reproduces the input. */
  text: string;
  kind: "step" | "attr" | "sep";
  targetId: string | null;
  targetKind?: SchemaNodeKind;
}

export interface ConstraintPathsResult {
  selector: PathToken[];
  fields: PathToken[][];
  /** The element(s) the selector's alternatives resolve to, in path order. */
  selectorTargets: ElementDecl[];
}

// --- Content-model flattening (shared by the resolver and exported for
// direct use / testing) ------------------------------------------------

// Resolves the complex type that governs an element's children, following an
// `<xs:element ref="…">` particle to its global declaration first (a ref
// particle carries no type of its own).
function resolveComplexTypeOf(el: ElementDecl, ctx: ResolveContext): ComplexType | null {
  const effective = resolveElementRef(el, ctx.indexById) ?? el;
  if (effective.type_inline_complex) return effective.type_inline_complex;
  if (effective.type_name) {
    const entry = resolveReference(effective.type_name, ctx.index, ["complexType"]);
    if (entry) return entry.node as ComplexType;
  }
  return null;
}

function flattenParticleElements(
  particle: Particle,
  ctx: ResolveContext,
  visited: Set<string>,
): ElementDecl[] {
  if (particle.kind === "element" && particle.element) return [particle.element];

  const group = particle.group_inline
    ? particle.group_inline
    : particle.kind === "group-ref" && particle.group_ref
      ? ((resolveReference(particle.group_ref, ctx.index, ["group"])?.node as Group | undefined) ?? null)
      : null;
  if (group) {
    if (visited.has(group.id)) return [];
    visited.add(group.id);
    return group.particle ? flattenParticleElements(group.particle, ctx, visited) : [];
  }

  // sequence | choice | all | any (wildcards contribute no name-testable element)
  const result: ElementDecl[] = [];
  for (const child of particle.children) result.push(...flattenParticleElements(child, ctx, visited));
  return result;
}

function flattenComplexTypeElements(
  ct: ComplexType,
  ctx: ResolveContext,
  visited: Set<string>,
): ElementDecl[] {
  if (visited.has(ct.id)) return [];
  visited.add(ct.id);
  const result: ElementDecl[] = [];
  if (ct.derivation === "extension" && ct.base) {
    const baseEntry = resolveReference(ct.base, ctx.index, ["complexType"]);
    if (baseEntry) {
      result.push(...flattenComplexTypeElements(baseEntry.node as ComplexType, ctx, visited));
    }
  }
  if (ct.particle) result.push(...flattenParticleElements(ct.particle, ctx, visited));
  return result;
}

// Direct child elements reachable from `el`'s type: follows an element ref
// first, then the extension base chain (base children before the type's own,
// per the base-then-own ordering the diagram/content-model views also use),
// group refs and inline groups, and sequence/choice/all compositors. Guarded
// against ref cycles by a visited set keyed on complex-type and group ids.
export function collectChildElements(el: ElementDecl, ctx: ResolveContext): ElementDecl[] {
  const ct = resolveComplexTypeOf(el, ctx);
  if (!ct) return [];
  return flattenComplexTypeElements(ct, ctx, new Set());
}

function flattenComplexTypeAttributes(
  ct: ComplexType,
  ctx: ResolveContext,
  visited: Set<string>,
): AttributeDecl[] {
  if (visited.has(ct.id)) return [];
  visited.add(ct.id);
  const result: AttributeDecl[] = [...ct.attributes];
  const seenGroups = new Set<string>();
  for (const ref of ct.attribute_group_refs) {
    const resolved: ResolvedAttribute[] = [];
    collectFromGroup(ref, ctx.index, seenGroups, resolved);
    result.push(...resolved.map((r) => r.attr));
  }
  if (ct.derivation === "extension" && ct.base) {
    const baseEntry = resolveReference(ct.base, ctx.index, ["complexType"]);
    if (baseEntry) {
      result.push(...flattenComplexTypeAttributes(baseEntry.node as ComplexType, ctx, visited));
    }
  }
  return result;
}

// Attributes reachable from `el`'s type: own attributes, attribute-group refs
// (flattened recursively), and the extension base chain.
export function collectAttributes(el: ElementDecl, ctx: ResolveContext): AttributeDecl[] {
  const ct = resolveComplexTypeOf(el, ctx);
  if (!ct) return [];
  return flattenComplexTypeAttributes(ct, ctx, new Set());
}

// --- Step-name helpers ---------------------------------------------------

function localName(qnameOrName: string): string {
  return qnameOrName.includes(":") ? qnameOrName.split(":").pop()! : qnameOrName;
}

function elementLocalName(el: ElementDecl): string | null {
  const raw = el.name ?? el.ref;
  return raw != null ? localName(raw) : null;
}

function attributeLocalName(attr: AttributeDecl): string | null {
  const raw = attr.name ?? attr.ref;
  return raw != null ? localName(raw) : null;
}

const WILDCARD_RE = /^([A-Za-z_][\w.-]*:)?\*$/;

interface ParsedStep {
  kind: "step" | "attr";
  /** Name-test text with any child::/attribute::/@ prefix stripped. */
  core: string;
  self: boolean;
  wildcard: boolean;
}

function parseStep(raw: string): ParsedStep {
  if (raw === ".") return { kind: "step", core: raw, self: true, wildcard: false };

  let kind: "step" | "attr" = "step";
  let core = raw;
  if (core.startsWith("attribute::")) {
    kind = "attr";
    core = core.slice("attribute::".length);
  } else if (core.startsWith("@")) {
    kind = "attr";
    core = core.slice(1);
  } else if (core.startsWith("child::")) {
    core = core.slice("child::".length);
  }
  return { kind, core, self: false, wildcard: WILDCARD_RE.test(core) };
}

// BFS over descendants (children, grandchildren, …) for `.//NameTest`, capped
// at MAX_DESCENDANT_DEPTH levels and guarded by a visited set keyed on
// element id — both matter for a recursive schema (an element whose type
// (transitively) contains itself), where the search would otherwise never
// terminate on a non-matching name.
function findDescendantElement(
  start: ElementDecl,
  ctx: ResolveContext,
  name: string,
): ElementDecl | null {
  const visited = new Set<string>();
  let frontier: ElementDecl[] = [start];
  for (let depth = 0; depth < MAX_DESCENDANT_DEPTH && frontier.length > 0; depth++) {
    const next: ElementDecl[] = [];
    for (const el of frontier) {
      if (visited.has(el.id)) continue;
      visited.add(el.id);
      for (const child of collectChildElements(el, ctx)) {
        if (elementLocalName(child) === name) return child;
        next.push(child);
      }
    }
    frontier = next;
  }
  return null;
}

// --- Step resolution -------------------------------------------------------

interface StepResolution {
  token: PathToken;
  nextContext: ElementDecl | null;
}

function resolveStep(
  raw: string,
  context: ElementDecl | null,
  ctx: ResolveContext,
  descendant: boolean,
): StepResolution {
  const parsed = parseStep(raw);

  if (context === null) {
    // Context was already lost by an earlier unresolved/wildcard step —
    // stay plain without attempting a match.
    return { token: { text: raw, kind: parsed.kind, targetId: null }, nextContext: null };
  }

  if (parsed.self) {
    return {
      token: { text: raw, kind: "step", targetId: context.id, targetKind: "element" },
      nextContext: context,
    };
  }

  if (parsed.wildcard) {
    // "*" / "ns:*" matches any name — we can't pin a single target, and we
    // can no longer say what type governs the next step either.
    return { token: { text: raw, kind: parsed.kind, targetId: null }, nextContext: null };
  }

  const name = localName(parsed.core);

  if (parsed.kind === "attr") {
    const match = collectAttributes(context, ctx).find((a) => attributeLocalName(a) === name);
    if (match) {
      return {
        token: { text: raw, kind: "attr", targetId: match.id, targetKind: "attribute" },
        nextContext: null, // attributes have no children of their own
      };
    }
    return { token: { text: raw, kind: "attr", targetId: null }, nextContext: null };
  }

  const match = descendant
    ? findDescendantElement(context, ctx, name)
    : collectChildElements(context, ctx).find((e) => elementLocalName(e) === name) ?? null;

  if (match) {
    return {
      token: { text: raw, kind: "step", targetId: match.id, targetKind: "element" },
      nextContext: match,
    };
  }
  return { token: { text: raw, kind: "step", targetId: null }, nextContext: null };
}

interface SinglePathResolution {
  tokens: PathToken[];
  finalContext: ElementDecl | null;
}

function resolveSinglePath(
  pathText: string,
  start: ElementDecl | null,
  ctx: ResolveContext,
): SinglePathResolution {
  const tokens: PathToken[] = [];
  let text = pathText;
  let descendant = false;
  if (text.startsWith(".//")) {
    tokens.push({ text: ".//", kind: "sep", targetId: null });
    text = text.slice(3);
    descendant = true;
  }

  let context = start;
  const stepTexts = text.split("/");
  stepTexts.forEach((stepText, i) => {
    if (i > 0) tokens.push({ text: "/", kind: "sep", targetId: null });
    const { token, nextContext } = resolveStep(stepText, context, ctx, i === 0 && descendant);
    tokens.push(token);
    context = nextContext;
  });

  return { tokens, finalContext: context };
}

// Splits `Paths ::= Path ('|' Path)*` into alternating path/separator chunks,
// keeping whitespace around '|' attached to the separator so token text stays
// verbatim.
function splitUnion(path: string): { text: string; isSep: boolean }[] {
  const re = /\s*\|\s*/g;
  const pieces: { text: string; isSep: boolean }[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(path))) {
    pieces.push({ text: path.slice(lastIndex, m.index), isSep: false });
    pieces.push({ text: m[0], isSep: true });
    lastIndex = m.index + m[0].length;
  }
  pieces.push({ text: path.slice(lastIndex), isSep: false });
  return pieces;
}

interface PathsResolution {
  tokens: PathToken[];
  finalContexts: ElementDecl[];
}

function resolvePathsInternal(
  path: string,
  start: ElementDecl | null,
  ctx: ResolveContext,
): PathsResolution {
  const tokens: PathToken[] = [];
  const finalContexts: ElementDecl[] = [];
  for (const piece of splitUnion(path)) {
    if (piece.isSep) {
      tokens.push({ text: piece.text, kind: "sep", targetId: null });
      continue;
    }
    const { tokens: pathTokens, finalContext } = resolveSinglePath(piece.text, start, ctx);
    tokens.push(...pathTokens);
    if (finalContext) finalContexts.push(finalContext);
  }
  return { tokens, finalContexts };
}

// Resolves one selector or field XPath string (which may itself be a `|`
// union of paths) relative to `start`, into a token chain suitable for
// rendering as a clickable step chain.
export function resolveConstraintPath(
  path: string,
  start: ElementDecl | null,
  ctx: ResolveContext,
): PathToken[] {
  return resolvePathsInternal(path, start, ctx).tokens;
}

// Resolves an identity constraint's selector and fields as a unit: fields are
// evaluated relative to the *first* element the selector resolves to (XSD
// identity constraints scope fields to the selector's matched node set; we
// only have the schema, not an instance, so the first resolvable alternative
// stands in for "the selected node").
export function resolveConstraintPaths(
  constraint: IdentityConstraint,
  host: ElementDecl,
  ctx: ResolveContext,
): ConstraintPathsResult {
  const selectorResolution = resolvePathsInternal(constraint.selector, host, ctx);
  const fieldStart = selectorResolution.finalContexts[0] ?? null;
  const fields = constraint.fields.map((field) => resolveConstraintPath(field, fieldStart, ctx));
  return {
    selector: selectorResolution.tokens,
    fields,
    selectorTargets: selectorResolution.finalContexts,
  };
}
