// Flattens the schema model into a visible row list respecting the current
// expand/collapse and filter state. Kept separate from the component so it
// can be unit-tested.

import type {
  ComplexType,
  ElementDecl,
  NodeIndexEntry,
  Particle,
  SchemaModel,
  SchemaNodeKind,
  SimpleType,
} from "../../types/schema";
import { resolveReference } from "../../lib/indexSchema";

export interface TreeRow {
  id: string;
  depth: number;
  kind: SchemaNodeKind;
  label: string;
  hasChildren: boolean;
  occurs?: string | null;
  typeHint?: string | null;
}

function formatOccurs(min: number, max: number | "unbounded"): string | null {
  if (min === 1 && max === 1) return null;
  const maxStr = max === "unbounded" ? "∞" : String(max);
  return `[${min}..${maxStr}]`;
}

export function buildTreeRows(
  model: SchemaModel,
  expandedIds: Set<string>,
  filterKinds: Set<SchemaNodeKind>,
  indexById: Map<string, NodeIndexEntry>,
): TreeRow[] {
  const rows: TreeRow[] = [];
  // Keep track of types visited during the current descent so a self-referencing
  // complex type (possible via xs:extension chains) doesn't blow the stack.
  const stackSeen: string[] = [];

  const pushRow = (row: TreeRow) => {
    if (!filterKinds.has(row.kind)) return;
    rows.push(row);
  };

  const particleHasVisible = (particle: Particle): boolean => {
    if (particle.element) return true;
    if (particle.group_inline) return true;
    if (particle.group_ref) return true;
    return particle.children.some(particleHasVisible);
  };

  const expandParticle = (particle: Particle, depth: number) => {
    if (particle.element) {
      descendElement(particle.element, depth, particle);
      return;
    }
    if (particle.group_inline) {
      rows.push({
        id: particle.group_inline.id,
        depth,
        kind: "group",
        label: particle.group_inline.name ?? "(inline group)",
        hasChildren: particle.group_inline.particle != null,
        occurs: formatOccurs(particle.min_occurs, particle.max_occurs),
      });
      if (
        expandedIds.has(particle.group_inline.id) &&
        particle.group_inline.particle
      ) {
        expandParticle(particle.group_inline.particle, depth + 1);
      }
      return;
    }
    if (particle.group_ref) {
      rows.push({
        id: `ref:${particle.group_ref}`,
        depth,
        kind: "group",
        label: particle.group_ref,
        hasChildren: false,
        occurs: formatOccurs(particle.min_occurs, particle.max_occurs),
      });
      return;
    }
    // Compositor (sequence/choice/all/any) — flatten its children at this depth.
    for (const child of particle.children) {
      expandParticle(child, depth);
    }
  };

  const descendElement = (element: ElementDecl, depth: number, hostParticle?: Particle) => {
    const rowId = element.id;
    const typeHint = element.type_name ?? null;
    const hasChildren =
      element.type_inline_complex != null ||
      element.type_inline_simple != null ||
      element.type_name != null;
    pushRow({
      id: rowId,
      depth,
      kind: "element",
      label: element.name ?? element.ref ?? "(anonymous)",
      hasChildren,
      occurs: hostParticle
        ? formatOccurs(hostParticle.min_occurs, hostParticle.max_occurs)
        : null,
      typeHint,
    });

    if (!expandedIds.has(rowId) || !filterKinds.has("element")) return;

    if (element.type_inline_complex) {
      descendComplex(element.type_inline_complex, depth + 1);
    } else if (element.type_name) {
      const resolved = resolveReference(
        element.type_name,
        Array.from(indexById.values()),
        ["complexType", "simpleType"],
      );
      if (resolved && !stackSeen.includes(resolved.id)) {
        stackSeen.push(resolved.id);
        if (resolved.kind === "complexType") {
          descendComplex(resolved.node as ComplexType, depth + 1);
        } else {
          describeSimple(resolved.node as SimpleType, depth + 1);
        }
        stackSeen.pop();
      }
    }
  };

  const descendComplex = (complex: ComplexType, depth: number) => {
    if (complex.particle && particleHasVisible(complex.particle)) {
      expandParticle(complex.particle, depth);
    }
    for (const attr of complex.attributes) {
      pushRow({
        id: attr.id,
        depth,
        kind: "attribute",
        label: "@" + (attr.name ?? attr.ref ?? "?"),
        hasChildren: false,
        typeHint: attr.type_name,
      });
    }
  };

  const describeSimple = (_simple: SimpleType, _depth: number) => {
    // Simple types add no visible children in the tree — facets live in the
    // detail panel — so this is a no-op.
  };

  // Top-level entry points: start with global elements, then global types.
  for (const element of model.elements) {
    descendElement(element, 0);
  }
  if (filterKinds.has("complexType")) {
    for (const complex of model.complex_types) {
      pushRow({
        id: complex.id,
        depth: 0,
        kind: "complexType",
        label: complex.name ?? "(anonymous)",
        hasChildren: complex.particle != null || complex.attributes.length > 0,
      });
      if (expandedIds.has(complex.id)) {
        descendComplex(complex, 1);
      }
    }
  }
  if (filterKinds.has("simpleType")) {
    for (const simple of model.simple_types) {
      pushRow({
        id: simple.id,
        depth: 0,
        kind: "simpleType",
        label: simple.name ?? "(anonymous)",
        hasChildren: false,
        typeHint: simple.base,
      });
    }
  }
  if (filterKinds.has("group")) {
    for (const group of model.groups) {
      pushRow({
        id: group.id,
        depth: 0,
        kind: "group",
        label: group.name ?? group.ref ?? "(anonymous)",
        hasChildren: group.particle != null,
      });
      if (expandedIds.has(group.id) && group.particle) {
        expandParticle(group.particle, 1);
      }
    }
  }
  if (filterKinds.has("attributeGroup")) {
    for (const ag of model.attribute_groups) {
      pushRow({
        id: ag.id,
        depth: 0,
        kind: "attributeGroup",
        label: ag.name ?? ag.ref ?? "(anonymous)",
        hasChildren: ag.attributes.length > 0,
      });
      if (expandedIds.has(ag.id)) {
        for (const attr of ag.attributes) {
          pushRow({
            id: attr.id,
            depth: 1,
            kind: "attribute",
            label: "@" + (attr.name ?? attr.ref ?? "?"),
            hasChildren: false,
            typeHint: attr.type_name,
          });
        }
      }
    }
  }
  if (filterKinds.has("attribute")) {
    for (const attr of model.attributes) {
      pushRow({
        id: attr.id,
        depth: 0,
        kind: "attribute",
        label: "@" + (attr.name ?? attr.ref ?? "?"),
        hasChildren: false,
        typeHint: attr.type_name,
      });
    }
  }

  return rows;
}
