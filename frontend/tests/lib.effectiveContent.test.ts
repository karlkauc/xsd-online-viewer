import { describe, expect, it } from "vitest";
import {
  effectiveAttributes,
  effectiveParticle,
  makeIndexComplexResolver,
  type ComplexResolver,
} from "../src/lib/effectiveContent";
import type { AttributeDecl, ComplexType, NodeIndexEntry, Particle } from "../src/types/schema";

function particle(kind: Particle["kind"], overrides: Partial<Particle> = {}): Particle {
  return {
    kind,
    min_occurs: 1,
    max_occurs: 1,
    element: null,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
    ...overrides,
  };
}

function complexType(overrides: Partial<ComplexType> & { id: string; name: string }): ComplexType {
  return {
    anonymous: false,
    abstract: false,
    mixed: false,
    content_kind: "complex",
    derivation: "none",
    base: null,
    particle: null,
    attributes: [],
    attribute_group_refs: [],
    simple_content_base: null,
    simple_content_facets: [],
    annotation: null,
    source_ref: null,
    ...overrides,
  };
}

function attr(id: string, name: string): AttributeDecl {
  return {
    id,
    name,
    qname: null,
    ref: null,
    type_name: "xs:string",
    type_inline: null,
    use: "optional",
    default: null,
    fixed: null,
    form: null,
    target_namespace: null,
    is_global: false,
    annotation: null,
    source_ref: null,
  };
}

function makeResolver(types: ComplexType[]): ComplexResolver {
  const byName = new Map(types.map((t) => [t.name, t]));
  return (qname) => {
    if (!qname) return undefined;
    const local = qname.includes(":") ? qname.split(":").pop()! : qname;
    return byName.get(local);
  };
}

describe("effectiveParticle", () => {
  it("returns the base particle when the extension adds no particle of its own", () => {
    const basePart = particle("sequence", { children: [particle("element")] });
    const base = complexType({ id: "c:Base", name: "Base", particle: basePart });
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "extension",
      base: "tns:Base",
      particle: null,
    });
    const resolver = makeResolver([base, derived]);

    const result = effectiveParticle(derived, resolver);
    expect(result.particle).toBe(basePart);
    expect(result.inheritedFrom).toEqual(["Base"]);
  });

  it("synthesizes a sequence(base, own) when both exist", () => {
    const basePart = particle("sequence", { children: [particle("element")] });
    const ownPart = particle("sequence", { children: [particle("element")] });
    const base = complexType({ id: "c:Base", name: "Base", particle: basePart });
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "extension",
      base: "tns:Base",
      particle: ownPart,
    });
    const resolver = makeResolver([base, derived]);

    const result = effectiveParticle(derived, resolver);
    expect(result.particle).not.toBeNull();
    expect(result.particle!.kind).toBe("sequence");
    expect(result.particle!.children).toEqual([basePart, ownPart]);
    expect(result.inheritedFrom).toEqual(["Base"]);
  });

  it("walks a two-level extension chain, base content first", () => {
    const grandPart = particle("element");
    const grand = complexType({ id: "c:Grand", name: "Grand", particle: grandPart });
    const parentOwn = particle("element");
    const parent = complexType({
      id: "c:Parent",
      name: "Parent",
      derivation: "extension",
      base: "tns:Grand",
      particle: parentOwn,
    });
    const childOwn = particle("element");
    const child = complexType({
      id: "c:Child",
      name: "Child",
      derivation: "extension",
      base: "tns:Parent",
      particle: childOwn,
    });
    const resolver = makeResolver([grand, parent, child]);

    const result = effectiveParticle(child, resolver);
    // parent's effective = sequence(grand, parentOwn); child's effective =
    // sequence(parent-effective, childOwn) -> content order grand, parent, child.
    expect(result.particle!.kind).toBe("sequence");
    const [left, right] = result.particle!.children;
    expect(right).toBe(childOwn);
    expect(left.kind).toBe("sequence");
    expect(left.children).toEqual([grandPart, parentOwn]);
    expect(result.inheritedFrom).toEqual(["Grand", "Parent"]);
  });

  it("returns the own particle unchanged for a restriction", () => {
    const ownPart = particle("sequence");
    const base = complexType({ id: "c:Base", name: "Base", particle: particle("element") });
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "restriction",
      base: "tns:Base",
      particle: ownPart,
    });
    const resolver = makeResolver([base, derived]);

    const result = effectiveParticle(derived, resolver);
    expect(result.particle).toBe(ownPart);
    expect(result.inheritedFrom).toEqual([]);
  });

  it("returns the own particle unchanged when derivation is none", () => {
    const ownPart = particle("sequence");
    const derived = complexType({ id: "c:Plain", name: "Plain", particle: ownPart });
    const result = effectiveParticle(derived, makeResolver([derived]));
    expect(result.particle).toBe(ownPart);
    expect(result.inheritedFrom).toEqual([]);
  });

  it("falls back to the own particle when the base is unresolvable", () => {
    const ownPart = particle("sequence");
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "extension",
      base: "tns:Missing",
      particle: ownPart,
    });
    const result = effectiveParticle(derived, makeResolver([derived]));
    expect(result.particle).toBe(ownPart);
    expect(result.inheritedFrom).toEqual([]);
  });

  it("terminates on a cycle (A extends B extends A)", () => {
    const a = complexType({
      id: "c:A",
      name: "A",
      derivation: "extension",
      base: "tns:B",
      particle: particle("element"),
    });
    const b = complexType({
      id: "c:B",
      name: "B",
      derivation: "extension",
      base: "tns:A",
      particle: particle("element"),
    });
    const resolver = makeResolver([a, b]);
    // Must return rather than blow the stack / loop forever.
    const result = effectiveParticle(a, resolver);
    expect(result.particle).not.toBeNull();
  });
});

describe("effectiveAttributes", () => {
  it("merges base-first, own last, de-duplicated by attribute id", () => {
    const baseAttr = attr("a:base", "id");
    const base = complexType({ id: "c:Base", name: "Base", attributes: [baseAttr] });
    const ownAttr = attr("a:own", "name");
    const dupAttr = attr("a:base", "id"); // same id as baseAttr — should not duplicate
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "extension",
      base: "tns:Base",
      attributes: [ownAttr, dupAttr],
    });
    const resolver = makeResolver([base, derived]);

    const result = effectiveAttributes(derived, resolver);
    expect(result.attributes).toEqual([baseAttr, ownAttr]);
    expect(result.inheritedFrom).toEqual(["Base"]);
  });

  it("merges attribute-group refs base-first", () => {
    const base = complexType({
      id: "c:Base",
      name: "Base",
      attribute_group_refs: ["tns:BaseGroup"],
    });
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "extension",
      base: "tns:Base",
      attribute_group_refs: ["tns:OwnGroup"],
    });
    const result = effectiveAttributes(derived, makeResolver([base, derived]));
    expect(result.attributeGroupRefs).toEqual(["tns:BaseGroup", "tns:OwnGroup"]);
  });

  it("returns own attributes unchanged for a restriction", () => {
    const ownAttr = attr("a:own", "name");
    const base = complexType({ id: "c:Base", name: "Base", attributes: [attr("a:base", "id")] });
    const derived = complexType({
      id: "c:Derived",
      name: "Derived",
      derivation: "restriction",
      base: "tns:Base",
      attributes: [ownAttr],
    });
    const result = effectiveAttributes(derived, makeResolver([base, derived]));
    expect(result.attributes).toEqual([ownAttr]);
    expect(result.inheritedFrom).toEqual([]);
  });
});

describe("makeIndexComplexResolver", () => {
  it("resolves a complexType by qname from a NodeIndexEntry list", () => {
    const node = complexType({ id: "complexType:Foo", name: "Foo" });
    const index: NodeIndexEntry[] = [
      {
        id: node.id,
        kind: "complexType",
        label: "Foo",
        qname: "Foo",
        source_ref: null,
        node,
      },
    ];
    const resolver = makeIndexComplexResolver(index);
    expect(resolver("Foo")).toBe(node);
    expect(resolver("tns:Foo")).toBe(node);
    expect(resolver("Missing")).toBeUndefined();
    expect(resolver(null)).toBeUndefined();
  });

  it("memoises lookups per qname", () => {
    const node = complexType({ id: "complexType:Foo", name: "Foo" });
    let calls = 0;
    const index: NodeIndexEntry[] = [
      {
        id: node.id,
        kind: "complexType",
        label: "Foo",
        qname: "Foo",
        source_ref: null,
        get node() {
          calls += 1;
          return node;
        },
      } as unknown as NodeIndexEntry,
    ];
    const resolver = makeIndexComplexResolver(index);
    resolver("Foo");
    resolver("Foo");
    resolver("Foo");
    expect(calls).toBe(1);
  });
});
