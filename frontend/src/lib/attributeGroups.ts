import type { AttributeDecl, AttributeGroup, NodeIndexEntry, Wildcard } from "../types/schema";
import { resolveReference } from "./indexSchema";

export interface ResolvedAttribute {
  attr: AttributeDecl;
  /** Origin label when the attribute was pulled in via a referenced group. */
  origin: string | null;
}

// Recursively resolves an attribute-group ref (and any nested
// attributeGroup refs it carries) into a flat list of attributes, tagging
// each with the group it came from. `seen` guards against ref cycles.
export function collectFromGroup(
  ref: string,
  index: NodeIndexEntry[],
  seen: Set<string>,
  out: ResolvedAttribute[],
): void {
  const entry = resolveReference(ref, index, ["attributeGroup"]);
  if (!entry) return;
  if (seen.has(entry.id)) return;
  seen.add(entry.id);
  const ag = entry.node as AttributeGroup;
  for (const a of ag.attributes) out.push({ attr: a, origin: entry.label });
  for (const nested of ag.attribute_group_refs) {
    collectFromGroup(nested, index, seen, out);
  }
}

export interface ResolvedWildcard {
  wildcard: Wildcard;
  /** Origin label when the wildcard comes from a referenced group. */
  origin: string | null;
}

// The xs:anyAttribute wildcards of the referenced attribute groups (nested
// refs included), each tagged with the group it sits in.
export function collectGroupWildcards(refs: string[], index: NodeIndexEntry[]): ResolvedWildcard[] {
  const out: ResolvedWildcard[] = [];
  const seen = new Set<string>();
  const visit = (ref: string) => {
    const entry = resolveReference(ref, index, ["attributeGroup"]);
    if (!entry || seen.has(entry.id)) return;
    seen.add(entry.id);
    const ag = entry.node as AttributeGroup;
    if (ag.any_attribute) out.push({ wildcard: ag.any_attribute, origin: entry.label });
    ag.attribute_group_refs.forEach(visit);
  };
  refs.forEach(visit);
  return out;
}

// Which names a wildcard admits, in the schema's own vocabulary:
// "##any" when nothing is said, "not …" for the XSD 1.1 exclusions.
export function wildcardNamespaceLabel(wildcard: Wildcard): string {
  const parts: string[] = [];
  if (wildcard.namespace) parts.push(wildcard.namespace);
  if (wildcard.not_namespace) parts.push(`not ${wildcard.not_namespace}`);
  if (wildcard.not_qname) parts.push(`not ${wildcard.not_qname}`);
  return parts.length ? parts.join(", ") : "##any";
}
