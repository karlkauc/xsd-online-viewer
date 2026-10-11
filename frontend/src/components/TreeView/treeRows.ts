// Flattens the schema model into a visible row list respecting the current
// expand/collapse and filter state. Kept separate from the component so it
// can be unit-tested.

import type {
  ComplexType,
  ElementDecl,
  IdentityConstraint,
  NodeIndexEntry,
  Particle,
  SchemaModel,
  SchemaNodeKind,
  SimpleType,
} from "../../types/schema";
import { redefinedOriginalIds, resolveElementRef, resolveReference } from "../../lib/indexSchema";
import { wildcardNamespaceLabel } from "../../lib/attributeGroups";
import { computeRootElements } from "../../lib/rootElements";
import { effectiveAttributes, effectiveParticle, makeIndexComplexResolver } from "../../lib/effectiveContent";

export interface TreeRow {
  id: string;
  depth: number;
  kind: SchemaNodeKind;
  label: string;
  hasChildren: boolean;
  occurs?: string | null;
  typeHint?: string | null;
  /** Number of xs:key/xs:keyref/xs:unique constraints declared on this
   *  (ref-resolved) element — see DetailPanel's IdentityConstraintsList. */
  constraintCount?: number;
  /** "key bookKey, keyref loanBookRef, …" — used as the ⚿ glyph's title. */
  constraintTitle?: string | null;
  /** An xs:any / xs:anyAttribute / open-content / xs:alternative row: no
   *  declaration of its own. */
  wildcard?: boolean;
  /** What a click selects when the row itself is not a declaration. */
  selectId?: string;
  title?: string | null;
}

function formatConstraintTitle(constraints: IdentityConstraint[]): string | null {
  if (!constraints.length) return null;
  return constraints.map((c) => `${c.kind} ${c.name}`).join(", ");
}

function formatOccurs(min: number, max: number | "unbounded"): string {
  // Always render so every tree row carries an occurrence pill — exact (1),
  // optional (0..1), repeatable (1..∞), bounded range (2..5).
  const maxStr = max === "unbounded" ? "∞" : String(max);
  if (min === max) return String(min);
  return `${min}..${maxStr}`;
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
  // Built once per call and memoised per qname — an "expand all" walks the
  // same base chain for many nodes, and this resolver backs both the extension
  // base lookups below and effectiveParticle/effectiveAttributes' own cycle
  // guards.
  const complexResolver = makeIndexComplexResolver(Array.from(indexById.values()), model.files);
  const redefined = redefinedOriginalIds(model);
  // Wildcards have no id of their own; a running number keeps the rows apart.
  let wildcardCount = 0;

  const pushRow = (row: TreeRow) => {
    if (!filterKinds.has(row.kind)) return;
    rows.push(row);
  };

  const particleHasVisible = (particle: Particle): boolean => {
    if (particle.element || particle.kind === "any") return true;
    if (particle.group_inline) return true;
    if (particle.group_ref) return true;
    return particle.children.some(particleHasVisible);
  };

  const expandParticle = (particle: Particle, depth: number, ownerId?: string) => {
    if (particle.element) {
      descendElement(particle.element, depth, particle);
      return;
    }
    if (particle.kind === "any") {
      const namespaces = wildcardNamespaceLabel({
        namespace: particle.wildcard_namespace,
        not_namespace: particle.wildcard_not_namespace ?? null,
        not_qname: particle.wildcard_not_qname ?? null,
      });
      pushRow({
        id: `any:${ownerId ?? ""}:${wildcardCount++}`,
        depth,
        kind: "element",
        label: `any ${namespaces}`,
        hasChildren: false,
        occurs: formatOccurs(particle.min_occurs, particle.max_occurs),
        typeHint: particle.wildcard_process_contents ?? "strict",
        wildcard: true,
        selectId: ownerId,
        title: `xs:any — any element from: ${namespaces}`,
      });
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
        expandParticle(particle.group_inline.particle, depth + 1, particle.group_inline.id);
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
      expandParticle(child, depth, ownerId);
    }
  };

  // Whether descendComplex() would emit at least one row for this type —
  // the effective (base-merged) particle must contain something visible, or
  // there must be effective attributes. A `<xs:simpleContent>` extension of
  // xs:string with no attributes has neither and must not get a toggle.
  const complexHasVisible = (complex: ComplexType): boolean => {
    const { particle } = effectiveParticle(complex, complexResolver);
    if (particle && particleHasVisible(particle)) return true;
    if (complex.open_content && complex.open_content.mode !== "none" && complex.open_content.wildcard) {
      return true;
    }
    const attributes = effectiveAttributes(complex, complexResolver);
    return attributes.attributes.length > 0 || attributes.completeAnyAttribute != null;
  };

  // Mirrors descendElementBody(): only a complex type (inline or resolved)
  // with visible content yields child rows. A built-in (xs:date), a named
  // simple type, an inline simple type or an unresolvable type all render
  // as leaves — expanding them would show nothing.
  const elementHasVisible = (element: ElementDecl): boolean => {
    if (element.alternatives?.length) return true;
    if (element.type_inline_complex) return complexHasVisible(element.type_inline_complex);
    if (!element.type_name) return false;
    const complex = complexResolver(element.type_name);
    return complex ? complexHasVisible(complex) : false;
  };

  const descendElement = (element: ElementDecl, depth: number, hostParticle?: Particle) => {
    const rowId = element.id;
    // An `<xs:element ref="…">` particle carries no content of its own — the
    // referenced global declaration holds the type. Descend through it so a
    // ref into an imported namespace (ds:Signature) is drillable too.
    const target = resolveElementRef(element, indexById) ?? element;
    const typeHint = target.type_name ?? null;
    const hasChildren = elementHasVisible(target);
    const constraints: IdentityConstraint[] = target.identity_constraints ?? [];
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
      constraintCount: constraints.length || undefined,
      constraintTitle: formatConstraintTitle(constraints),
    });

    if (!expandedIds.has(rowId) || !filterKinds.has("element")) return;
    // Guard against a reference cycle (A refs B refs A) blowing the stack.
    if (target !== element) {
      if (stackSeen.includes(target.id)) return;
      stackSeen.push(target.id);
      descendElementBody(target, depth, rowId);
      stackSeen.pop();
      return;
    }
    descendElementBody(target, depth, rowId);
  };

  const descendElementBody = (element: ElementDecl, depth: number, rowId: string) => {
    if (element.type_inline_complex) {
      descendComplex(element.type_inline_complex, depth + 1, rowId);
    } else if (element.type_name) {
      const resolved = resolveReference(
        element.type_name,
        Array.from(indexById.values()),
        ["complexType", "simpleType"],
      );
      if (resolved && !stackSeen.includes(resolved.id)) {
        stackSeen.push(resolved.id);
        if (resolved.kind === "complexType") {
          descendComplex(resolved.node as ComplexType, depth + 1, rowId);
        } else {
          describeSimple(resolved.node as SimpleType, depth + 1);
        }
        stackSeen.pop();
      }
    }
    descendAlternatives(element, depth + 1);
  };

  // XSD 1.1 xs:alternative: the type the element has when a test holds. One
  // row per alternative, after the content of the declared type; expanding
  // it shows what that type contains.
  const descendAlternatives = (element: ElementDecl, depth: number) => {
    (element.alternatives ?? []).forEach((alternative, i) => {
      const named = alternative.type_name
        ? resolveReference(alternative.type_name, Array.from(indexById.values()), [
            "complexType",
            "simpleType",
          ])
        : undefined;
      const complex =
        alternative.type_inline_complex ??
        (named?.kind === "complexType" ? (named.node as ComplexType) : null);
      const rowId = `alternative:${element.id}:${i}`;
      const typeId =
        named?.id ?? alternative.type_inline_complex?.id ?? alternative.type_inline_simple?.id;
      rows.push({
        id: rowId,
        depth,
        kind: complex || !typeId ? "complexType" : "simpleType",
        label: alternative.test == null ? "else" : `if ${alternative.test}`,
        hasChildren: complex != null && complexHasVisible(complex),
        typeHint:
          alternative.type_name ?? (typeId ? "(inline type)" : "(no type)"),
        wildcard: true,
        selectId: typeId ?? element.id,
        title:
          alternative.test == null
            ? "xs:alternative — the type when no test holds"
            : `xs:alternative — the type when this holds: ${alternative.test}`,
      });
      if (complex && expandedIds.has(rowId) && !stackSeen.includes(complex.id)) {
        stackSeen.push(complex.id);
        descendComplex(complex, depth + 1, typeId ?? element.id);
        stackSeen.pop();
      }
    });
  };

  const descendComplex = (complex: ComplexType, depth: number, ownerId: string) => {
    const { particle } = effectiveParticle(complex, complexResolver);
    if (particle && particleHasVisible(particle)) {
      expandParticle(particle, depth, ownerId);
    }
    // XSD 1.1 open content: elements the type admits beside its content model.
    const open = complex.open_content;
    if (open && open.mode !== "none" && open.wildcard && filterKinds.has("element")) {
      const namespaces = wildcardNamespaceLabel(open.wildcard);
      rows.push({
        id: `openContent:${ownerId}:${wildcardCount++}`,
        depth,
        kind: "element",
        label: `open: any ${namespaces}`,
        hasChildren: false,
        occurs: "0..∞",
        typeHint: `${open.mode} · ${open.wildcard.process_contents ?? "strict"}`,
        wildcard: true,
        selectId: ownerId,
        title:
          open.mode === "suffix"
            ? `xs:openContent — any element from: ${namespaces}, after the declared content`
            : `xs:openContent — any element from: ${namespaces}, anywhere between the declared content`,
      });
    }
    const { attributes, completeAnyAttribute } = effectiveAttributes(complex, complexResolver);
    for (const attr of attributes) {
      pushRow({
        id: attr.id,
        depth,
        kind: "attribute",
        label: "@" + (attr.name ?? attr.ref ?? "?"),
        hasChildren: false,
        typeHint: attr.type_name,
      });
    }
    if (completeAnyAttribute) {
      pushRow({
        id: `anyAttribute:${ownerId}:${wildcardCount++}`,
        depth,
        kind: "attribute",
        label: `@any ${wildcardNamespaceLabel(completeAnyAttribute)}`,
        hasChildren: false,
        typeHint: completeAnyAttribute.process_contents ?? "strict",
        wildcard: true,
        selectId: ownerId,
        title: `xs:anyAttribute — any attribute from: ${wildcardNamespaceLabel(completeAnyAttribute)}`,
      });
    }
  };

  const describeSimple = (_simple: SimpleType, _depth: number) => {
    // Simple types add no visible children in the tree — facets live in the
    // detail panel — so this is a no-op.
  };

  // Top-level entry points: start with the document-root elements, then
  // global types. Only globals that aren't referenced elsewhere count as
  // roots — see computeRootElements().
  for (const element of computeRootElements(model)) {
    descendElement(element, 0);
  }
  if (filterKinds.has("complexType")) {
    for (const complex of model.complex_types) {
      if (redefined.has(complex.id)) continue;
      pushRow({
        id: complex.id,
        depth: 0,
        kind: "complexType",
        label: complex.name ?? "(anonymous)",
        hasChildren: complexHasVisible(complex),
      });
      if (expandedIds.has(complex.id)) {
        descendComplex(complex, 1, complex.id);
      }
    }
  }
  if (filterKinds.has("simpleType")) {
    for (const simple of model.simple_types) {
      if (redefined.has(simple.id)) continue;
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
      if (redefined.has(group.id)) continue;
      pushRow({
        id: group.id,
        depth: 0,
        kind: "group",
        label: group.name ?? group.ref ?? "(anonymous)",
        hasChildren: group.particle != null,
      });
      if (expandedIds.has(group.id) && group.particle) {
        expandParticle(group.particle, 1, group.id);
      }
    }
  }
  if (filterKinds.has("attributeGroup")) {
    for (const ag of model.attribute_groups) {
      if (redefined.has(ag.id)) continue;
      pushRow({
        id: ag.id,
        depth: 0,
        kind: "attributeGroup",
        label: ag.name ?? ag.ref ?? "(anonymous)",
        hasChildren: ag.attributes.length > 0 || ag.any_attribute != null,
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
        if (ag.any_attribute) {
          pushRow({
            id: `anyAttribute:${ag.id}:${wildcardCount++}`,
            depth: 1,
            kind: "attribute",
            label: `@any ${wildcardNamespaceLabel(ag.any_attribute)}`,
            hasChildren: false,
            typeHint: ag.any_attribute.process_contents ?? "strict",
            wildcard: true,
            selectId: ag.id,
            title: `xs:anyAttribute — any attribute from: ${wildcardNamespaceLabel(ag.any_attribute)}`,
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
  if (filterKinds.has("notation")) {
    for (const notation of model.notations ?? []) {
      pushRow({
        id: notation.id,
        depth: 0,
        kind: "notation",
        label: notation.name,
        hasChildren: false,
        typeHint: notation.public ?? notation.system,
      });
    }
  }

  return rows;
}
