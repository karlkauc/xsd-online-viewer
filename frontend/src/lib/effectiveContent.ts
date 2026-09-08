// Computes the *effective* content model / attribute list of a complex type,
// folding in whatever an `xs:extension` base chain contributes.
//
// XSD defines extension content as `sequence(base content, own content)` —
// the base's particle comes first, then the type's own. A type derived by
// `xs:restriction`, or not derived at all (`derivation === "none"`), only
// ever narrows or repeats its base explicitly, so its own particle/attributes
// already say everything there is to say; we don't walk further in that case
// (mirrors `collectComplexAssertions`'s "restriction narrows, doesn't
// inherit unstated content" stance — but for particles/attributes, unlike
// assertions, restriction is genuinely self-contained since XSD requires a
// restricting type to repeat the effective content it keeps).
//
// Three structural views (TreeView, ContentModelView, DiagramView) each read
// a type's OWN `particle`/`attributes` directly, which is wrong for an
// extension whose own particle is null (e.g. FundsXML's
// `<xs:extension base="BenchmarkStaticDataType"/>` with no additional
// content) — they show nothing instead of the base's content. This module is
// the single place that walks the base chain so all three agree.
//
// Pure — no store access. Callers supply a `ComplexResolver` appropriate to
// their context (`makeIndexComplexResolver` for the flat NodeIndexEntry list
// used by TreeView/ContentModelView; buildGraph builds its own small
// resolver over its Map-based type index).

import type { AttributeDecl, ComplexType, NodeIndexEntry, Particle, QName } from "../types/schema";
import { resolveReference } from "./indexSchema";

export type ComplexResolver = (qname: string | null | undefined) => ComplexType | undefined;

export interface EffectiveParticleResult {
  particle: Particle | null;
  /** Base type names contributing content, outermost (furthest ancestor)
   *  first — matches the order their content appears in the synthesized
   *  sequence. */
  inheritedFrom: string[];
}

export interface EffectiveAttributesResult {
  attributes: AttributeDecl[];
  attributeGroupRefs: QName[];
  /** Base type names contributing attributes, outermost first. */
  inheritedFrom: string[];
}

// Wraps a base particle and a type's own particle in a synthetic sequence —
// `xs:extension` content is `sequence(base content, own content)`.
function synthesizeSequence(base: Particle, own: Particle): Particle {
  return {
    kind: "sequence",
    min_occurs: 1,
    max_occurs: 1,
    element: null,
    group_ref: null,
    group_inline: null,
    children: [base, own],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

export function effectiveParticle(
  complex: ComplexType,
  resolve: ComplexResolver,
  seen: Set<string> = new Set(),
): EffectiveParticleResult {
  if (complex.derivation !== "extension" || !complex.base || seen.has(complex.id)) {
    return { particle: complex.particle, inheritedFrom: [] };
  }
  const base = resolve(complex.base);
  if (!base) {
    return { particle: complex.particle, inheritedFrom: [] };
  }
  const nextSeen = new Set(seen);
  nextSeen.add(complex.id);
  const baseResult = effectiveParticle(base, resolve, nextSeen);
  const inheritedFrom = base.name
    ? [...baseResult.inheritedFrom, base.name]
    : baseResult.inheritedFrom;

  const ownParticle = complex.particle;
  if (baseResult.particle && ownParticle) {
    return { particle: synthesizeSequence(baseResult.particle, ownParticle), inheritedFrom };
  }
  return { particle: baseResult.particle ?? ownParticle, inheritedFrom };
}

export function effectiveAttributes(
  complex: ComplexType,
  resolve: ComplexResolver,
  seen: Set<string> = new Set(),
): EffectiveAttributesResult {
  if (complex.derivation !== "extension" || !complex.base || seen.has(complex.id)) {
    return {
      attributes: complex.attributes,
      attributeGroupRefs: complex.attribute_group_refs,
      inheritedFrom: [],
    };
  }
  const base = resolve(complex.base);
  if (!base) {
    return {
      attributes: complex.attributes,
      attributeGroupRefs: complex.attribute_group_refs,
      inheritedFrom: [],
    };
  }
  const nextSeen = new Set(seen);
  nextSeen.add(complex.id);
  const baseResult = effectiveAttributes(base, resolve, nextSeen);
  const inheritedFrom = base.name
    ? [...baseResult.inheritedFrom, base.name]
    : baseResult.inheritedFrom;

  const seenIds = new Set<string>();
  const attributes: AttributeDecl[] = [];
  for (const attr of [...baseResult.attributes, ...complex.attributes]) {
    if (seenIds.has(attr.id)) continue;
    seenIds.add(attr.id);
    attributes.push(attr);
  }
  const attributeGroupRefs = Array.from(
    new Set([...baseResult.attributeGroupRefs, ...complex.attribute_group_refs]),
  );
  return { attributes, attributeGroupRefs, inheritedFrom };
}

// Resolver backed by the flat NodeIndexEntry list (TreeView, ContentModelView).
// Memoised per qname so repeatedly walking the same base chain (e.g. the
// tree's "expand all") doesn't rescan the index for every node.
export function makeIndexComplexResolver(index: NodeIndexEntry[]): ComplexResolver {
  const cache = new Map<string, ComplexType | undefined>();
  return (qname) => {
    if (!qname) return undefined;
    if (cache.has(qname)) return cache.get(qname);
    const entry = resolveReference(qname, index, ["complexType"]);
    const result = entry ? (entry.node as ComplexType) : undefined;
    cache.set(qname, result);
    return result;
  };
}
