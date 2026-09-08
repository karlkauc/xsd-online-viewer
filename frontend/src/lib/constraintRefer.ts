import type { IdentityConstraint } from "../types/schema";

export interface ReferTarget {
  hostId: string;
  name: string;
}

// A keyref's `refer_id` is resolved by the backend whenever the referenced
// key/unique constraint exists in this schema. When it's null (a dangling
// `refer`, or a fixture/model that didn't resolve it), fall back to matching
// the `refer` QName's local name against every known constraint's own name
// before giving up — the raw QName's prefix binding isn't validated by this
// viewer, so a local-name match is the best honest guess. Shared by
// IdentityConstraintsList.tsx (detail panel) and
// ContentModelView/IdentityConstraintsTable.tsx (centre pane).
export function resolveReferTarget(
  constraint: IdentityConstraint,
  constraintsById: Map<string, { constraint: IdentityConstraint; hostId: string }>,
): ReferTarget | null {
  if (constraint.refer_id) {
    const entry = constraintsById.get(constraint.refer_id);
    if (entry) return { hostId: entry.hostId, name: entry.constraint.name };
  }
  if (constraint.refer) {
    const local = constraint.refer.includes(":")
      ? constraint.refer.split(":").pop()!
      : constraint.refer;
    for (const entry of constraintsById.values()) {
      if (entry.constraint.name === local) {
        return { hostId: entry.hostId, name: entry.constraint.name };
      }
    }
  }
  return null;
}
