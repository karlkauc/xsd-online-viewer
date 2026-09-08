import type { AttributeDecl, AttributeGroup, NodeIndexEntry } from "../types/schema";
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
