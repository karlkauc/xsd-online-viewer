// Walks a SchemaModel once to build a flat index used by the tree,
// command palette and cross-reference ("Find Usages") features.

import type {
  AttributeDecl,
  AttributeGroup,
  ComplexType,
  ElementDecl,
  Group,
  NodeIndexEntry,
  OverrideDirective,
  OverrideReplacement,
  Particle,
  SchemaModel,
  SchemaNodeKind,
  SimpleType,
} from "../types/schema";

export interface IndexBundle {
  index: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
  // Maps a referenced-type qname (e.g. "tns:AddressType") -> nodes that
  // reference it. Used by "Find Usages".
  usagesByTarget: Map<string, NodeIndexEntry[]>;
  // Child id -> parent id, used by the Breadcrumb to reconstruct the full
  // ancestor path of the current selection.
  parentById: Map<string, string>;
  // XSD 1.1 ``xs:override`` cross-references. Replacement-id → directive
  // and the replacement entry itself; original (kind+qname) → list of
  // replacements that apply to it.
  overrideByReplacementId: Map<
    string,
    { directive: OverrideDirective; replacement: OverrideReplacement }
  >;
  overridesByOriginalKey: Map<string, OverrideReplacement[]>;
}

export function buildIndex(model: SchemaModel): IndexBundle {
  const entries: NodeIndexEntry[] = [];
  const usagesByTarget = new Map<string, NodeIndexEntry[]>();
  const parentById = new Map<string, string>();

  const addUsage = (target: string | null | undefined, entry: NodeIndexEntry) => {
    if (!target) return;
    const list = usagesByTarget.get(target) ?? [];
    list.push(entry);
    usagesByTarget.set(target, list);
  };

  const setParent = (childId: string, parentId: string | null) => {
    if (!parentId) return;
    if (parentById.has(childId)) return;
    parentById.set(childId, parentId);
  };

  const visitElement = (element: ElementDecl, parentId: string | null) => {
    const entry: NodeIndexEntry = {
      id: element.id,
      kind: "element",
      label: element.name ?? element.ref ?? "(anonymous)",
      qname: element.qname,
      source_ref: element.source_ref,
      node: element,
    };
    entries.push(entry);
    setParent(element.id, parentId);
    addUsage(element.type_name, entry);
    if (element.type_inline_complex) visitComplexType(element.type_inline_complex, element.id);
    if (element.type_inline_simple) visitSimpleType(element.type_inline_simple, element.id);
  };

  // Particles are transparent — they don't appear in the breadcrumb path, so
  // the declared parent passes straight through to their children.
  const visitParticle = (particle: Particle, parentId: string | null) => {
    if (particle.element) visitElement(particle.element, parentId);
    if (particle.group_inline) visitGroup(particle.group_inline, parentId);
    for (const child of particle.children) visitParticle(child, parentId);
  };

  const visitComplexType = (complex: ComplexType, parentId: string | null) => {
    const entry: NodeIndexEntry = {
      id: complex.id,
      kind: "complexType",
      label: complex.name ?? "(anonymous)",
      qname: complex.name ?? null,
      source_ref: complex.source_ref,
      node: complex,
    };
    entries.push(entry);
    setParent(complex.id, parentId);
    addUsage(complex.base, entry);
    addUsage(complex.simple_content_base, entry);
    // For inline anonymous complex types the enclosing element is already
    // the declared parent — skip this level so the breadcrumb doesn't get
    // cluttered with "(anonymous)".
    const childParentId = complex.name ? complex.id : parentId;
    if (complex.particle) visitParticle(complex.particle, childParentId);
    for (const attr of complex.attributes) visitAttribute(attr, childParentId);
  };

  const visitSimpleType = (simple: SimpleType, parentId: string | null) => {
    const entry: NodeIndexEntry = {
      id: simple.id,
      kind: "simpleType",
      label: simple.name ?? "(anonymous)",
      qname: simple.name ?? null,
      source_ref: simple.source_ref,
      node: simple,
    };
    entries.push(entry);
    setParent(simple.id, parentId);
    addUsage(simple.base, entry);
    addUsage(simple.item_type, entry);
    for (const member of simple.member_types) addUsage(member, entry);
    if (simple.item_inline) visitSimpleType(simple.item_inline, simple.id);
    for (const m of simple.member_inline) visitSimpleType(m, simple.id);
  };

  const visitAttribute = (attr: AttributeDecl, parentId: string | null) => {
    const entry: NodeIndexEntry = {
      id: attr.id,
      kind: "attribute",
      label: attr.name ?? attr.ref ?? "(anonymous)",
      qname: attr.qname,
      source_ref: attr.source_ref,
      node: attr,
    };
    entries.push(entry);
    setParent(attr.id, parentId);
    addUsage(attr.type_name, entry);
    if (attr.type_inline) visitSimpleType(attr.type_inline, attr.id);
  };

  const visitGroup = (group: Group, parentId: string | null) => {
    const entry: NodeIndexEntry = {
      id: group.id,
      kind: "group",
      label: group.name ?? group.ref ?? "(anonymous)",
      qname: group.name,
      source_ref: group.source_ref,
      node: group,
    };
    entries.push(entry);
    setParent(group.id, parentId);
    if (group.particle) visitParticle(group.particle, group.id);
  };

  const visitAttributeGroup = (ag: AttributeGroup, parentId: string | null) => {
    const entry: NodeIndexEntry = {
      id: ag.id,
      kind: "attributeGroup",
      label: ag.name ?? ag.ref ?? "(anonymous)",
      qname: ag.name,
      source_ref: ag.source_ref,
      node: ag,
    };
    entries.push(entry);
    setParent(ag.id, parentId);
    for (const attr of ag.attributes) visitAttribute(attr, ag.id);
  };

  for (const element of model.elements) visitElement(element, null);
  for (const attr of model.attributes) visitAttribute(attr, null);
  for (const simple of model.simple_types) visitSimpleType(simple, null);
  for (const complex of model.complex_types) visitComplexType(complex, null);
  for (const group of model.groups) visitGroup(group, null);
  for (const ag of model.attribute_groups) visitAttributeGroup(ag, null);

  const indexById = new Map<string, NodeIndexEntry>();
  for (const entry of entries) indexById.set(entry.id, entry);

  const overrideByReplacementId = new Map<
    string,
    { directive: OverrideDirective; replacement: OverrideReplacement }
  >();
  const overridesByOriginalKey = new Map<string, OverrideReplacement[]>();
  for (const directive of model.overrides ?? []) {
    for (const replacement of directive.replacements) {
      overrideByReplacementId.set(replacement.replacement_id, {
        directive,
        replacement,
      });
      const key = overrideKey(replacement.kind, replacement.qname);
      const list = overridesByOriginalKey.get(key) ?? [];
      list.push(replacement);
      overridesByOriginalKey.set(key, list);
    }
  }

  return {
    index: entries,
    indexById,
    usagesByTarget,
    parentById,
    overrideByReplacementId,
    overridesByOriginalKey,
  };
}

// Stable key for cross-referencing an original declaration with its override
// replacements. Replacements carry the qname produced by the parser
// (Clark-form for namespaced names, bare local otherwise).
export function overrideKey(kind: string, qname: string): string {
  return `${kind}:${qname}`;
}

// Resolve a QName reference from a declaration to an entry in the index.
// Handles the common case of matching by qname (namespace-qualified) or by
// bare local name when no namespace prefix is present.
export function resolveReference(
  ref: string,
  index: NodeIndexEntry[],
  kinds: SchemaNodeKind[],
): NodeIndexEntry | undefined {
  const local = ref.includes(":") ? ref.split(":").pop()! : ref;
  return index.find((entry) => {
    if (!kinds.includes(entry.kind)) return false;
    if (entry.qname === ref) return true;
    if (entry.label === local) return true;
    return false;
  });
}
