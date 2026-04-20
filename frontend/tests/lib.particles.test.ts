import { describe, expect, it } from "vitest";
import { flattenParticle } from "../src/lib/particles";
import type { ElementDecl, Particle } from "../src/types/schema";

function leaf(name: string): ElementDecl {
  return {
    id: `element:test/${name}`,
    name,
    qname: null,
    ref: null,
    type_name: "xs:string",
    type_inline_simple: null,
    type_inline_complex: null,
    min_occurs: 1,
    max_occurs: 1,
    default: null,
    fixed: null,
    nillable: false,
    abstract: false,
    substitution_group: null,
    form: null,
    target_namespace: null,
    is_global: false,
    annotation: null,
    source_ref: null,
  };
}

function elementParticle(element: ElementDecl, min = 1, max: number | "unbounded" = 1): Particle {
  return {
    kind: "element",
    min_occurs: min,
    max_occurs: max,
    element,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

function compositor(
  kind: "sequence" | "choice" | "all",
  children: Particle[],
  min = 1,
  max: number | "unbounded" = 1,
): Particle {
  return {
    kind,
    min_occurs: min,
    max_occurs: max,
    element: null,
    group_ref: null,
    group_inline: null,
    children,
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

describe("flattenParticle", () => {
  it("returns [] for null input", () => {
    expect(flattenParticle(null)).toEqual([]);
  });

  it("unwraps the outer compositor and emits children at depth 0", () => {
    const root = compositor("sequence", [
      elementParticle(leaf("A")),
      elementParticle(leaf("B")),
      elementParticle(leaf("C")),
    ]);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(3);
    expect(rows.every((r) => r.depth === 0)).toBe(true);
    expect(rows.map((r) => r.element?.name)).toEqual(["A", "B", "C"]);
    expect(rows.every((r) => r.compositor === undefined)).toBe(true);
  });

  it("emits a header row for nested compositors and their children at depth+1", () => {
    const inner = compositor("choice", [
      elementParticle(leaf("X")),
      elementParticle(leaf("Y")),
    ]);
    const root = compositor("sequence", [
      elementParticle(leaf("A")),
      inner,
      elementParticle(leaf("B")),
    ]);
    const rows = flattenParticle(root);
    expect(rows.map((r) => ({
      depth: r.depth,
      label: r.element?.name ?? r.compositor ?? r.ellipsis,
    }))).toEqual([
      { depth: 0, label: "A" },
      { depth: 0, label: "choice" },
      { depth: 1, label: "X" },
      { depth: 1, label: "Y" },
      { depth: 0, label: "B" },
    ]);
  });

  it("renders group-ref as a single non-expanded row", () => {
    const groupRef: Particle = {
      kind: "group-ref",
      min_occurs: 1,
      max_occurs: "unbounded",
      element: null,
      group_ref: "tns:NameGroup",
      group_inline: null,
      children: [],
      wildcard_namespace: null,
      wildcard_process_contents: null,
      annotation: null,
    };
    const root = compositor("sequence", [
      elementParticle(leaf("A")),
      groupRef,
    ]);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(2);
    expect(rows[1]).toMatchObject({
      depth: 0,
      groupRef: "tns:NameGroup",
      occurs: "1..*",
    });
  });

  it("renders any (wildcard) as a single row with namespace and processContents", () => {
    const wildcard: Particle = {
      kind: "any",
      min_occurs: 0,
      max_occurs: "unbounded",
      element: null,
      group_ref: null,
      group_inline: null,
      children: [],
      wildcard_namespace: "##other",
      wildcard_process_contents: "lax",
      annotation: null,
    };
    const root = compositor("sequence", [wildcard]);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      depth: 0,
      any: { namespace: "##other", processContents: "lax" },
      occurs: "0..*",
    });
  });

  it("collapses depth >2 into a single ellipsis row at the deeper level", () => {
    // sequence > choice > sequence > sequence > element ("DeepLeaf")
    // After unwrapping the outer sequence:
    //   choice@0, sequence@1, sequence@2, then a child at depth 3 → collapsed.
    const deepLeaf = elementParticle(leaf("DeepLeaf"));
    const lvl3 = compositor("sequence", [deepLeaf]);
    const lvl2 = compositor("sequence", [lvl3]);
    const lvl1 = compositor("choice", [lvl2]);
    const root = compositor("sequence", [lvl1]);

    const rows = flattenParticle(root);
    expect(rows.map((r) => ({
      depth: r.depth,
      label: r.compositor ?? (r.ellipsis ? "…" : r.element?.name),
    }))).toEqual([
      { depth: 0, label: "choice" },
      { depth: 1, label: "sequence" },
      { depth: 2, label: "sequence" },
      { depth: 3, label: "…" },
    ]);
    const ellipsis = rows[3];
    expect(ellipsis.ellipsis).toContain("DeepLeaf");
  });

  it("formats occurs as min..max with * for unbounded", () => {
    const root = compositor("sequence", [
      elementParticle(leaf("Once"), 1, 1),
      elementParticle(leaf("Optional"), 0, 1),
      elementParticle(leaf("ZeroToMany"), 0, "unbounded"),
      elementParticle(leaf("OneToMany"), 1, "unbounded"),
    ]);
    const rows = flattenParticle(root);
    expect(rows.map((r) => r.occurs)).toEqual([
      "1..1",
      "0..1",
      "0..*",
      "1..*",
    ]);
  });

  it("walks a non-compositor root particle (single-element top) without unwrapping", () => {
    const root = elementParticle(leaf("Solo"), 0, 1);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ depth: 0, occurs: "0..1" });
    expect(rows[0].element?.name).toBe("Solo");
  });
});
