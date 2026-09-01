// Walks a SchemaModel and returns the IDs of every element whose content
// model is expandable in the diagram (i.e. it has a resolvable ComplexType
// with a particle). Cycles in the type graph are guarded by tracking the
// complex types already visited.

import type {
  ComplexType,
  ElementDecl,
  Particle,
  SchemaModel,
} from "../types/schema";

function buildComplexIndex(model: SchemaModel): Map<string, ComplexType> {
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

function resolveComplex(
  typeRef: string | null | undefined,
  index: Map<string, ComplexType>,
): ComplexType | undefined {
  if (!typeRef) return undefined;
  const direct = index.get(typeRef);
  if (direct) return direct;
  const local = typeRef.includes(":") ? typeRef.split(":").pop()! : typeRef;
  return index.get(local);
}

export function collectExpandableElementIds(model: SchemaModel): Set<string> {
  const result = new Set<string>();
  const index = buildComplexIndex(model);
  const globalsById = new Map(model.elements.map((e) => [e.id, e]));
  const seenComplex = new Set<string>();

  function visitElement(element: ElementDecl): void {
    // A ref particle carries no type of its own — the declaration it points
    // at does, so expand-all must follow it (ds:Signature & co.).
    const declaration =
      (element.ref && element.ref_id ? globalsById.get(element.ref_id) : undefined) ??
      element;
    const complex =
      declaration.type_inline_complex ??
      resolveComplex(declaration.type_name, index);
    if (!complex) return;
    result.add(element.id);
    if (seenComplex.has(complex.id)) return;
    seenComplex.add(complex.id);
    if (complex.particle) visitParticle(complex.particle);
  }

  function visitParticle(particle: Particle): void {
    if (particle.element) visitElement(particle.element);
    for (const child of particle.children) visitParticle(child);
  }

  for (const element of model.elements) visitElement(element);
  return result;
}
