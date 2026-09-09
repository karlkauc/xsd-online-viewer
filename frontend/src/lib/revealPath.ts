// Which ids must be expanded so that navigating to `targetId` reveals it in
// the tree and the diagram. Each XPath segment is the id of an element (or
// attribute leaf), but the tree descent passes through the enclosing named
// complexType too — we add each element's direct `parentById` entry to
// cover that (treeRows.ts resolves type references on the fly when
// expanding, so the intermediate complexType must be expanded as well).
// The target itself is never included: revealing must not toggle it open.

import type { NodeIndexEntry } from "../types/schema";
import { computeXPath } from "./xpath";

export function collectRevealIds(
  targetId: string,
  indexById: Map<string, NodeIndexEntry>,
  parentById: Map<string, string>,
): string[] {
  const segments = computeXPath(targetId, indexById, parentById);
  if (!segments || segments.length === 0) return [];
  const targetIdx = segments.length - 1;
  const ids = new Set<string>();
  for (let i = 0; i < targetIdx; i++) {
    const seg = segments[i];
    ids.add(seg.id);
    const parent = parentById.get(seg.id);
    if (parent) ids.add(parent);
  }
  // For attribute targets, expand the host element too.
  const target = segments[targetIdx];
  if (target.isAttribute && targetIdx > 0) {
    ids.add(segments[targetIdx - 1].id);
  }
  return Array.from(ids);
}
