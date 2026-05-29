// Determines which global elements are "document roots" — i.e. elements that
// can legitimately start an instance document.
//
// The parser merges the top-level <xs:element> declarations of the main file
// AND every <xs:include>/<xs:import>ed file into one flat ``model.elements``
// list. Rendering all of them as diagram/tree roots is noisy: an included
// schema's globals (e.g. the building blocks behind FundsXML4) show up as
// peers of the real root. We instead show only the globals that are never
// referenced (via ``ref=``) anywhere in the schema — those are the actual
// document entry points.
//
// Note: substitution-group members (``substitution_group``) are intentionally
// NOT treated as references — they are alternative document roots in their own
// right and should still appear.

import type { ElementDecl, Particle, SchemaModel } from "../types/schema";

const localName = (qname: string): string =>
  qname.includes(":") ? qname.split(":").pop()! : qname;

// Walk every particle reachable from a global structure, collecting the
// ``ref`` of each element particle. Mirrors the descent rules of
// ``visitParticle``/``visitComplexType`` in indexSchema.ts.
function collectElementRefs(model: SchemaModel): Set<string> {
  const refs = new Set<string>();

  const walkParticle = (particle: Particle): void => {
    if (particle.element) {
      if (particle.element.ref) refs.add(particle.element.ref);
      // An element particle may carry an anonymous inline complex type whose
      // own content model can reference further globals.
      if (particle.element.type_inline_complex?.particle) {
        walkParticle(particle.element.type_inline_complex.particle);
      }
    }
    if (particle.group_inline?.particle) walkParticle(particle.group_inline.particle);
    for (const child of particle.children) walkParticle(child);
  };

  for (const complex of model.complex_types) {
    if (complex.particle) walkParticle(complex.particle);
  }
  for (const group of model.groups) {
    if (group.particle) walkParticle(group.particle);
  }
  for (const element of model.elements) {
    if (element.type_inline_complex?.particle) {
      walkParticle(element.type_inline_complex.particle);
    }
  }

  return refs;
}

// Returns the global elements that act as document roots: every element in
// ``model.elements`` that is not referenced by ``ref=`` somewhere in the
// schema. Falls back to the full list if nothing survives the filter (e.g. a
// schema whose only globals reference each other recursively) so the views
// never end up empty.
export function computeRootElements(model: SchemaModel): ElementDecl[] {
  const refs = collectElementRefs(model);
  if (refs.size === 0) return model.elements;

  // Resolve refs against global elements by qname or by bare local name —
  // same matching strategy as resolveReference() in indexSchema.ts.
  const localRefs = new Set<string>();
  for (const ref of refs) localRefs.add(localName(ref));

  const referencedIds = new Set<string>();
  for (const element of model.elements) {
    const matches =
      (element.qname != null && refs.has(element.qname)) ||
      (element.name != null && localRefs.has(element.name));
    if (matches) referencedIds.add(element.id);
  }

  const roots = model.elements.filter((el) => !referencedIds.has(el.id));
  return roots.length > 0 ? roots : model.elements;
}
