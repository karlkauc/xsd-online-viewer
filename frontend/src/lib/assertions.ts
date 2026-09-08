// Collects XSD 1.1 assertions (``xs:assert`` on complex types, ``xs:assertion``
// on simple types) *contributed by a type* to whatever declaration (element,
// attribute, or the type itself) is currently displayed.
//
// A declaration's own type may not be the only source of assertions: an
// extension chain (``xs:extension``/``xs:restriction`` on a complex or simple
// type) can assert at every level, and a complexType with simpleContent can
// have its base simple type assert too. This module walks those chains once
// so DetailPanel, ContentModelView and the diagram badge all agree on what
// "the assertions of this declaration" means.
//
// Pure — no store access. Callers supply a ``TypeResolver`` appropriate to
// their context (``makeIndexResolver`` for the flat NodeIndexEntry list used
// by the detail panels, ``makeModelResolver`` for the plain SchemaModel used
// by buildGraph).

import type {
  Assertion,
  AttributeDecl,
  ComplexType,
  ElementDecl,
  NodeIndexEntry,
  SchemaModel,
  SimpleType,
} from "../types/schema";
import { resolveReference } from "./indexSchema";

// One "layer" of assertions contributed by a single type in a base chain.
// ``from`` is the label of the type that declares these assertions — null
// when that type is the declaration's own (named or inline) type, so callers
// don't render a redundant "from <the type itself>" label.
export interface AssertionGroup {
  assertions: Assertion[];
  from: string | null;
  typeId: string;
}

export interface ResolvedType<T> {
  id: string;
  label: string;
  node: T;
}

export interface TypeResolver {
  resolveComplex(qname: string): ResolvedType<ComplexType> | undefined;
  resolveSimple(qname: string): ResolvedType<SimpleType> | undefined;
}

// Resolver backed by the flat NodeIndexEntry list (DetailPanel, ContentModelView).
export function makeIndexResolver(index: NodeIndexEntry[]): TypeResolver {
  return {
    resolveComplex(qname) {
      const entry = resolveReference(qname, index, ["complexType"]);
      if (!entry) return undefined;
      return { id: entry.id, label: entry.label, node: entry.node as ComplexType };
    },
    resolveSimple(qname) {
      const entry = resolveReference(qname, index, ["simpleType"]);
      if (!entry) return undefined;
      return { id: entry.id, label: entry.label, node: entry.node as SimpleType };
    },
  };
}

// Resolver backed by a plain SchemaModel (buildGraph, which builds its own
// Map-based indices rather than the full NodeIndexEntry list).
export function makeModelResolver(model: SchemaModel): TypeResolver {
  const complexByQName = new Map<string, ComplexType>();
  const simpleByQName = new Map<string, SimpleType>();
  const register = <T extends { name: string | null }>(
    map: Map<string, T>,
    node: T,
  ) => {
    if (!node.name) return;
    map.set(node.name, node);
    if (model.target_namespace) {
      map.set(`{${model.target_namespace}}${node.name}`, node);
    }
  };
  for (const c of model.complex_types) register(complexByQName, c);
  for (const s of model.simple_types) register(simpleByQName, s);

  const lookup = <T>(map: Map<string, T>, qname: string): T | undefined => {
    const direct = map.get(qname);
    if (direct) return direct;
    const local = qname.includes(":") ? qname.split(":").pop()! : qname;
    return map.get(local);
  };

  return {
    resolveComplex(qname) {
      const node = lookup(complexByQName, qname);
      return node ? { id: node.id, label: node.name ?? "(anonymous)", node } : undefined;
    },
    resolveSimple(qname) {
      const node = lookup(simpleByQName, qname);
      return node ? { id: node.id, label: node.name ?? "(anonymous)", node } : undefined;
    },
  };
}

// Own assertions + the xs:extension base chain, cycle-guarded by type id.
// When the chain bottoms out at a complexType with simpleContent whose base
// resolves to a simpleType (not a further complexType), the simple type's own
// restriction-base chain is folded in too.
export function collectComplexAssertions(
  complex: ComplexType,
  resolver: TypeResolver,
  ownLabel: string | null = null,
): AssertionGroup[] {
  const groups: AssertionGroup[] = [];
  const seen = new Set<string>();
  let current: ComplexType | undefined = complex;
  let label = ownLabel;
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    if (current.assertions?.length) {
      groups.push({ assertions: current.assertions, from: label, typeId: current.id });
    }
    if (current.derivation !== "extension" || !current.base) break;
    const resolvedComplex = resolver.resolveComplex(current.base);
    if (resolvedComplex) {
      current = resolvedComplex.node;
      label = resolvedComplex.label;
      continue;
    }
    if (current.content_kind === "simple") {
      const resolvedSimple = resolver.resolveSimple(current.base);
      if (resolvedSimple) {
        groups.push(
          ...collectSimpleAssertions(resolvedSimple.node, resolver, resolvedSimple.label),
        );
      }
    }
    break;
  }
  return groups;
}

// Own assertions + the xs:restriction base chain, cycle-guarded by type id.
export function collectSimpleAssertions(
  simple: SimpleType,
  resolver: TypeResolver,
  ownLabel: string | null = null,
): AssertionGroup[] {
  const groups: AssertionGroup[] = [];
  const seen = new Set<string>();
  let current: SimpleType | undefined = simple;
  let label = ownLabel;
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    if (current.assertions?.length) {
      groups.push({ assertions: current.assertions, from: label, typeId: current.id });
    }
    if (current.derivation !== "restriction" || !current.base) break;
    const resolved = resolver.resolveSimple(current.base);
    if (!resolved) break;
    current = resolved.node;
    label = resolved.label;
  }
  return groups;
}

// Assertions contributed by an element's type — inline or named, complex or
// simple — including the base chain in either case.
export function collectElementAssertions(
  element: ElementDecl,
  resolver: TypeResolver,
): AssertionGroup[] {
  if (element.type_inline_complex) {
    return collectComplexAssertions(element.type_inline_complex, resolver, null);
  }
  if (element.type_inline_simple) {
    return collectSimpleAssertions(element.type_inline_simple, resolver, null);
  }
  if (element.type_name) {
    const resolvedComplex = resolver.resolveComplex(element.type_name);
    if (resolvedComplex) {
      return collectComplexAssertions(resolvedComplex.node, resolver, resolvedComplex.label);
    }
    const resolvedSimple = resolver.resolveSimple(element.type_name);
    if (resolvedSimple) {
      return collectSimpleAssertions(resolvedSimple.node, resolver, resolvedSimple.label);
    }
  }
  return [];
}

// Assertions contributed by an attribute's (always simple) type.
export function collectAttributeAssertions(
  attribute: AttributeDecl,
  resolver: TypeResolver,
): AssertionGroup[] {
  if (attribute.type_inline) {
    return collectSimpleAssertions(attribute.type_inline, resolver, null);
  }
  if (attribute.type_name) {
    const resolved = resolver.resolveSimple(attribute.type_name);
    if (resolved) {
      return collectSimpleAssertions(resolved.node, resolver, resolved.label);
    }
  }
  return [];
}

export function countAssertions(groups: AssertionGroup[]): number {
  return groups.reduce((sum, g) => sum + g.assertions.length, 0);
}
