// Determines which global elements are document roots to render at the top
// level of the diagram and tree.
//
// The parser merges the top-level <xs:element> declarations of the main file
// AND every <xs:include>/<xs:import>ed file into one flat ``model.elements``
// list. Rendering all of them as roots is noisy: an included schema's globals
// (e.g. the ~24 globals of xmldsig-core-schema.xsd behind FundsXML) show up as
// peers of the real root. We therefore keep only the globals declared in the
// main file — the file the user actually loaded. Included declarations remain
// in the model (and are still reachable by reference), they just don't appear
// as standalone roots.

import type { ElementDecl, SchemaModel } from "../types/schema";

export function computeRootElements(model: SchemaModel): ElementDecl[] {
  // ``model.files`` marks exactly one source file as "main" (the loaded
  // entry point). Match elements back to it via their source_ref.file_id.
  const mainFileId = model.files.find((f) => f.relationship === "main")?.id;
  if (mainFileId == null) return model.elements;

  const roots = model.elements.filter(
    (el) => el.source_ref?.file_id === mainFileId,
  );

  // Safeguard: a main file that declares no globals of its own (a pure
  // include/import aggregator) would leave nothing to show — fall back to the
  // full list so the views are never empty.
  return roots.length > 0 ? roots : model.elements;
}

/**
 * Roots worth offering for a sample document: the named document roots minus
 * abstract elements nothing can substitute. Such an element can never be the
 * document element, so its sample could never validate (KML declares 113 of
 * its 269 globals like that). An abstract root with a concrete member stays:
 * the generator substitutes it. If nothing would be left, every named root is
 * offered as before.
 */
export function sampleRootCandidates(model: SchemaModel): ElementDecl[] {
  const named = computeRootElements(model).filter((el) => el.name);
  const membersByHead = new Map<string, ElementDecl[]>();
  for (const el of model.elements) {
    if (!el.substitution_group || !el.name) continue;
    // substitution_group is a prefixed QName; match on its local name.
    const head = localName(el.substitution_group);
    membersByHead.set(head, [...(membersByHead.get(head) ?? []), el]);
  }
  const substitutable = (el: ElementDecl, seen: Set<string>): boolean => {
    if (!el.abstract) return true;
    if (seen.has(el.id)) return false;
    seen.add(el.id);
    return (membersByHead.get(el.name ?? "") ?? []).some((member) => substitutable(member, seen));
  };
  const usable = named.filter((el) => substitutable(el, new Set()));
  return usable.length > 0 ? usable : named;
}

function localName(qname: string): string {
  return qname.slice(Math.max(qname.lastIndexOf("}"), qname.lastIndexOf(":")) + 1);
}
