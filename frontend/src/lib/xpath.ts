// Derives a document-instance XPath for the currently selected schema node.
//
// The Zustand `parentById` map follows the XSD declaration hierarchy, which
// for named types differs from the XML document hierarchy: an element that
// references a named complexType loses its parent-child link to the type's
// children (they parent to the complexType, not the containing element).
// This helper bridges that gap by replacing each named complexType ancestor
// with the first element that references it, reconstructing a path like
// `/FundsXML4/Funds/Fund/Identifiers` that matches what an instance document
// would look like.
//
// Returns `null` when no meaningful XPath can be derived (e.g. a stand-alone
// complexType / simpleType / group is selected, or a dangling reference).

import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  NodeIndexEntry,
} from "../types/schema";

export interface XPathSegment {
  id: string;
  label: string;
  isAttribute: boolean;
}

function localName(name: string): string {
  // Strip "{ns}" or "prefix:" to get a bare local name.
  const afterBrace = name.includes("}") ? name.split("}").pop()! : name;
  return afterBrace.includes(":") ? afterBrace.split(":").pop()! : afterBrace;
}

function elementLabel(element: ElementDecl): string {
  if (element.name) return element.name;
  if (element.ref) return localName(element.ref);
  return "(anonymous)";
}

function attributeLabel(attr: AttributeDecl): string {
  if (attr.name) return attr.name;
  if (attr.ref) return localName(attr.ref);
  return "?";
}

function findFirstElementReferencingType(
  typeName: string,
  indexById: Map<string, NodeIndexEntry>,
): NodeIndexEntry | null {
  const target = localName(typeName);
  for (const entry of indexById.values()) {
    if (entry.kind !== "element") continue;
    const element = entry.node as ElementDecl;
    if (!element.type_name) continue;
    if (localName(element.type_name) === target) return entry;
  }
  return null;
}

export function computeXPath(
  selectedId: string | null,
  indexById: Map<string, NodeIndexEntry>,
  parentById: Map<string, string>,
): XPathSegment[] | null {
  if (!selectedId) return null;
  const start = indexById.get(selectedId);
  if (!start) return null;
  // Only element/attribute selections have a document-instance XPath. Other
  // kinds (complexType, simpleType, group, attributeGroup) are declarations
  // without a single canonical path, so hide the bar in those cases.
  if (start.kind !== "element" && start.kind !== "attribute") return null;

  const segments: XPathSegment[] = [];
  const seen = new Set<string>();
  let cur: string | undefined = selectedId;
  let attributeSeen = false;
  // Iteration budget guards against pathological cycles even when `seen` is
  // defeated by re-entering via reverse-ref lookups.
  for (let i = 0; cur && i < 256; i++) {
    if (seen.has(cur)) break;
    seen.add(cur);
    const entry = indexById.get(cur);
    if (!entry) break;

    if (entry.kind === "attribute") {
      if (attributeSeen) break;
      attributeSeen = true;
      const attr = entry.node as AttributeDecl;
      segments.unshift({
        id: cur,
        label: `@${attributeLabel(attr)}`,
        isAttribute: true,
      });
      cur = parentById.get(cur);
      continue;
    }

    if (entry.kind === "element") {
      const element = entry.node as ElementDecl;
      segments.unshift({
        id: cur,
        label: elementLabel(element),
        isAttribute: false,
      });
      cur = parentById.get(cur);
      continue;
    }

    if (entry.kind === "complexType") {
      const complex = entry.node as ComplexType;
      if (complex.name) {
        const referencing = findFirstElementReferencingType(complex.name, indexById);
        if (!referencing) return null;
        cur = referencing.id;
        continue;
      }
      // Anonymous complexType — indexSchema flattens these transparently, so
      // walk past to the declared parent.
      cur = parentById.get(cur);
      continue;
    }

    // simpleType / group / attributeGroup are not representable in an XPath.
    return null;
  }

  return segments.length ? segments : null;
}
