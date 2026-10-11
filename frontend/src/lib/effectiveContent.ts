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

import type {
  AttributeDecl,
  AttributeGroup,
  ComplexType,
  NodeIndexEntry,
  Particle,
  QName,
  SourceFile,
  SourceRef,
  Wildcard,
} from "../types/schema";
import { resolveReference } from "./indexSchema";
import { completeWildcard, type SourcedWildcard } from "./wildcards";

export type ComplexResolver = ((qname: string | null | undefined) => ComplexType | undefined) & {
  /** Looks up an attribute group, for the wildcards the groups bring along. */
  attributeGroup?: (qname: string) => AttributeGroup | undefined;
  /** Target namespace of the file a declaration sits in; undefined when unknown. */
  targetNamespace?: (ref: SourceRef | null | undefined) => string | null | undefined;
};

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
  /** The type's own xs:anyAttribute, else the nearest one up the base chain. */
  anyAttribute: Wildcard | null;
  /**
   * The wildcard in effect: the own one intersected with those of the
   * attribute groups, united with the base type's for an extension.
   */
  completeAnyAttribute: Wildcard | null;
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

// A type's attribute groups, the one from its file's ``defaultAttributes`` included.
function ownAttributeGroupRefs(complex: ComplexType): QName[] {
  const implicit = complex.default_attributes;
  return implicit && !complex.attribute_group_refs.includes(implicit)
    ? [...complex.attribute_group_refs, implicit]
    : complex.attribute_group_refs;
}

// The type's own xs:anyAttribute and those of the attribute groups it uses.
function ownWildcards(complex: ComplexType, resolve: ComplexResolver): SourcedWildcard[] {
  const out: SourcedWildcard[] = [];
  if (complex.any_attribute) {
    out.push({
      wildcard: complex.any_attribute,
      target: resolve.targetNamespace?.(complex.source_ref),
    });
  }
  const seen = new Set<string>();
  const visit = (ref: string) => {
    const group = resolve.attributeGroup?.(ref);
    if (!group || seen.has(group.id)) return;
    seen.add(group.id);
    if (group.any_attribute) {
      out.push({
        wildcard: group.any_attribute,
        target: resolve.targetNamespace?.(group.source_ref),
      });
    }
    group.attribute_group_refs.forEach(visit);
  };
  ownAttributeGroupRefs(complex).forEach(visit);
  return out;
}

export function effectiveAttributes(
  complex: ComplexType,
  resolve: ComplexResolver,
  seen: Set<string> = new Set(),
): EffectiveAttributesResult {
  const target = resolve.targetNamespace?.(complex.source_ref);
  const base =
    complex.derivation === "extension" && complex.base && !seen.has(complex.id)
      ? resolve(complex.base)
      : undefined;
  if (!base) {
    return {
      attributes: complex.attributes,
      attributeGroupRefs: ownAttributeGroupRefs(complex),
      anyAttribute: complex.any_attribute ?? null,
      completeAnyAttribute: completeWildcard(ownWildcards(complex, resolve), null, target),
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
    new Set([...baseResult.attributeGroupRefs, ...ownAttributeGroupRefs(complex)]),
  );
  return {
    attributes,
    attributeGroupRefs,
    anyAttribute: complex.any_attribute ?? baseResult.anyAttribute,
    completeAnyAttribute: completeWildcard(
      ownWildcards(complex, resolve),
      baseResult.completeAnyAttribute
        ? {
            wildcard: baseResult.completeAnyAttribute,
            target: resolve.targetNamespace?.(base.source_ref),
          }
        : null,
      target,
    ),
    inheritedFrom,
  };
}

// Resolver backed by the flat NodeIndexEntry list (TreeView, ContentModelView).
// Memoised per qname so repeatedly walking the same base chain (e.g. the
// tree's "expand all") doesn't rescan the index for every node.
export function makeIndexComplexResolver(
  index: NodeIndexEntry[],
  files?: SourceFile[],
): ComplexResolver {
  const cache = new Map<string, ComplexType | undefined>();
  const resolver: ComplexResolver = (qname) => {
    if (!qname) return undefined;
    if (cache.has(qname)) return cache.get(qname);
    const entry = resolveReference(qname, index, ["complexType"]);
    const result = entry ? (entry.node as ComplexType) : undefined;
    cache.set(qname, result);
    return result;
  };
  resolver.attributeGroup = (qname) => {
    const entry = resolveReference(qname, index, ["attributeGroup"]);
    return entry ? (entry.node as AttributeGroup) : undefined;
  };
  if (files) {
    const namespaces = new Map(files.map((f) => [f.id, f.target_namespace]));
    resolver.targetNamespace = (ref) => (ref ? namespaces.get(ref.file_id) : undefined);
  }
  return resolver;
}
