// Walks a SchemaModel once to build a flat index used by the tree,
// command palette and cross-reference ("Find Usages") features.

import type {
  AttributeDecl,
  AttributeGroup,
  ComplexType,
  ElementDecl,
  Group,
  NodeIndexEntry,
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
}

export function buildIndex(model: SchemaModel): IndexBundle {
  const entries: NodeIndexEntry[] = [];
  const usagesByTarget = new Map<string, NodeIndexEntry[]>();

  const addUsage = (target: string | null | undefined, entry: NodeIndexEntry) => {
    if (!target) return;
    const list = usagesByTarget.get(target) ?? [];
    list.push(entry);
    usagesByTarget.set(target, list);
  };

  const visitElement = (element: ElementDecl) => {
    const entry: NodeIndexEntry = {
      id: element.id,
      kind: "element",
      label: element.name ?? element.ref ?? "(anonymous)",
      qname: element.qname,
      source_ref: element.source_ref,
      node: element,
    };
    entries.push(entry);
    addUsage(element.type_name, entry);
    if (element.type_inline_complex) visitComplexType(element.type_inline_complex);
    if (element.type_inline_simple) visitSimpleType(element.type_inline_simple);
  };

  const visitParticle = (particle: Particle) => {
    if (particle.element) visitElement(particle.element);
    if (particle.group_inline) visitGroup(particle.group_inline);
    for (const child of particle.children) visitParticle(child);
  };

  const visitComplexType = (complex: ComplexType) => {
    const entry: NodeIndexEntry = {
      id: complex.id,
      kind: "complexType",
      label: complex.name ?? "(anonymous)",
      qname: complex.name ?? null,
      source_ref: complex.source_ref,
      node: complex,
    };
    entries.push(entry);
    addUsage(complex.base, entry);
    addUsage(complex.simple_content_base, entry);
    if (complex.particle) visitParticle(complex.particle);
    for (const attr of complex.attributes) visitAttribute(attr);
  };

  const visitSimpleType = (simple: SimpleType) => {
    const entry: NodeIndexEntry = {
      id: simple.id,
      kind: "simpleType",
      label: simple.name ?? "(anonymous)",
      qname: simple.name ?? null,
      source_ref: simple.source_ref,
      node: simple,
    };
    entries.push(entry);
    addUsage(simple.base, entry);
    addUsage(simple.item_type, entry);
    for (const member of simple.member_types) addUsage(member, entry);
    if (simple.item_inline) visitSimpleType(simple.item_inline);
    for (const m of simple.member_inline) visitSimpleType(m);
  };

  const visitAttribute = (attr: AttributeDecl) => {
    const entry: NodeIndexEntry = {
      id: attr.id,
      kind: "attribute",
      label: attr.name ?? attr.ref ?? "(anonymous)",
      qname: attr.qname,
      source_ref: attr.source_ref,
      node: attr,
    };
    entries.push(entry);
    addUsage(attr.type_name, entry);
    if (attr.type_inline) visitSimpleType(attr.type_inline);
  };

  const visitGroup = (group: Group) => {
    const entry: NodeIndexEntry = {
      id: group.id,
      kind: "group",
      label: group.name ?? group.ref ?? "(anonymous)",
      qname: group.name,
      source_ref: group.source_ref,
      node: group,
    };
    entries.push(entry);
    if (group.particle) visitParticle(group.particle);
  };

  const visitAttributeGroup = (ag: AttributeGroup) => {
    const entry: NodeIndexEntry = {
      id: ag.id,
      kind: "attributeGroup",
      label: ag.name ?? ag.ref ?? "(anonymous)",
      qname: ag.name,
      source_ref: ag.source_ref,
      node: ag,
    };
    entries.push(entry);
    for (const attr of ag.attributes) visitAttribute(attr);
  };

  for (const element of model.elements) visitElement(element);
  for (const attr of model.attributes) visitAttribute(attr);
  for (const simple of model.simple_types) visitSimpleType(simple);
  for (const complex of model.complex_types) visitComplexType(complex);
  for (const group of model.groups) visitGroup(group);
  for (const ag of model.attribute_groups) visitAttributeGroup(ag);

  const indexById = new Map<string, NodeIndexEntry>();
  for (const entry of entries) indexById.set(entry.id, entry);

  return { index: entries, indexById, usagesByTarget };
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
