// Flattens an XSD particle tree into an indentation-aware row list for the
// Content Model table. The outer compositor is unwrapped; nested compositors
// emit their own header row. Recursion is capped at MAX_DEPTH; deeper subtrees
// collapse to a single ellipsis row whose `ellipsis` text serialises the
// elided sub-tree for a tooltip.

import type { ElementDecl, Particle, QName } from "../types/schema";

export const MAX_DEPTH = 2;

export type CompositorKind = "sequence" | "choice" | "all";

export interface FlatRow {
  /** Stable React key. */
  key: string;
  /** Indentation level. 0 = direct child of the unwrapped outer compositor. */
  depth: number;
  /** Formatted "min..max" string (e.g. "1..1", "0..*"). */
  occurs: string;
  /** When this row IS a nested compositor header. */
  compositor?: CompositorKind;
  /** When this row is an element leaf. */
  element?: ElementDecl;
  /** When this row is a group-ref leaf — the QName of the referenced group. */
  groupRef?: QName;
  /** When this row is a wildcard. */
  any?: { namespace: string | null; processContents: string | null };
  /** When this row is the collapse marker for an elided deep sub-tree. */
  ellipsis?: string;
}

export function flattenParticle(particle: Particle | null): FlatRow[] {
  const rows: FlatRow[] = [];
  if (!particle) return rows;

  if (particle.kind === "sequence" || particle.kind === "choice" || particle.kind === "all") {
    let counter = 0;
    for (const child of particle.children) {
      walk(child, 0, `r${counter++}`, rows);
    }
    return rows;
  }

  walk(particle, 0, "r0", rows);
  return rows;
}

function walk(
  particle: Particle,
  depth: number,
  keyPrefix: string,
  rows: FlatRow[],
): void {
  const occurs = formatOccurs(particle.min_occurs, particle.max_occurs);

  if (particle.kind === "element" && particle.element) {
    rows.push({
      key: `${keyPrefix}-el`,
      depth,
      occurs,
      element: particle.element,
    });
    return;
  }

  if (particle.kind === "group-ref") {
    rows.push({
      key: `${keyPrefix}-gr`,
      depth,
      occurs,
      groupRef: particle.group_ref ?? "(group)",
    });
    return;
  }

  if (particle.kind === "any") {
    rows.push({
      key: `${keyPrefix}-any`,
      depth,
      occurs,
      any: {
        namespace: particle.wildcard_namespace,
        processContents: particle.wildcard_process_contents,
      },
    });
    return;
  }

  // sequence | choice | all  → emit a header row, then walk children.
  rows.push({
    key: `${keyPrefix}-c`,
    depth,
    occurs,
    compositor: particle.kind as CompositorKind,
  });

  if (depth >= MAX_DEPTH) {
    rows.push({
      key: `${keyPrefix}-…`,
      depth: depth + 1,
      occurs: "",
      ellipsis: serialiseSubtree(particle, ""),
    });
    return;
  }

  let counter = 0;
  for (const child of particle.children) {
    walk(child, depth + 1, `${keyPrefix}-${counter++}`, rows);
  }
}

function formatOccurs(min: number, max: number | "unbounded"): string {
  const maxStr = max === "unbounded" ? "*" : String(max);
  return `${min}..${maxStr}`;
}

function serialiseSubtree(particle: Particle, indent: string): string {
  const occ = formatOccurs(particle.min_occurs, particle.max_occurs);
  const head = (() => {
    if (particle.kind === "element" && particle.element) {
      return `${particle.element.name ?? particle.element.ref ?? "?"} [${occ}]`;
    }
    if (particle.kind === "group-ref") {
      return `«group ${particle.group_ref ?? "?"}» [${occ}]`;
    }
    if (particle.kind === "any") {
      return `any [${occ}]`;
    }
    return `${particle.kind} [${occ}]`;
  })();
  const lines = [indent + head];
  for (const child of particle.children) {
    lines.push(serialiseSubtree(child, indent + "  "));
  }
  return lines.join("\n");
}
