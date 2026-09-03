import type { Annotation, Facet, SchemaNode } from "../types/schema";

/**
 * Secondary text a declaration can be found by: its documentation, XML
 * comments and enumeration values. Names are matched separately (and rank
 * higher); this catches "the element that says 'ISIN' in its docs".
 */
export function searchableText(node: SchemaNode): string {
  const parts: string[] = [];
  const annotation = (node as { annotation?: Annotation | null }).annotation;
  if (annotation) {
    for (const doc of annotation.documentation) parts.push(doc.text);
    for (const comment of annotation.comments) parts.push(comment);
  }
  for (const facets of facetLists(node)) {
    for (const facet of facets) if (facet.kind === "enumeration") parts.push(facet.value);
  }
  return parts.join(" \n ").replace(/\s+/g, " ").trim();
}

function facetLists(node: SchemaNode): Facet[][] {
  const lists: Facet[][] = [];
  const n = node as {
    facets?: Facet[];
    simple_content_facets?: Facet[];
    type_inline?: { facets?: Facet[] } | null;
    type_inline_simple?: { facets?: Facet[] } | null;
  };
  if (n.facets) lists.push(n.facets);
  if (n.simple_content_facets) lists.push(n.simple_content_facets);
  if (n.type_inline?.facets) lists.push(n.type_inline.facets);
  if (n.type_inline_simple?.facets) lists.push(n.type_inline_simple.facets);
  return lists;
}

/** A short window of `text` around the first occurrence of `needle` (case-insensitive). */
export function snippetAround(text: string, needle: string, radius = 40): string {
  const at = text.toLowerCase().indexOf(needle.toLowerCase());
  if (at < 0) return text.slice(0, radius * 2);
  const start = Math.max(0, at - radius);
  const end = Math.min(text.length, at + needle.length + radius);
  return `${start > 0 ? "…" : ""}${text.slice(start, end)}${end < text.length ? "…" : ""}`;
}
