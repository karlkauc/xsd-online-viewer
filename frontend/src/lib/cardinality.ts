/**
 * Visual classification of a particle's cardinality, shared by the views
 * that encode occurrence in styling (the diagram draws optional nodes with a
 * dashed border and repeating nodes with a thicker one).
 */
export interface OccursStyle {
  /** minOccurs = 0 — the particle may be absent. */
  optional: boolean;
  /** maxOccurs > 1 or unbounded — the particle may appear more than once. */
  repeating: boolean;
}

export function occursStyle(min: number, max: number | "unbounded"): OccursStyle {
  return {
    optional: min === 0,
    repeating: max === "unbounded" || max > 1,
  };
}
