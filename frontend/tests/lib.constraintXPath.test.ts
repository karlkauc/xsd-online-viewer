import { describe, expect, it } from "vitest";
import { buildIndex } from "../src/lib/indexSchema";
import {
  collectAttributes,
  collectChildElements,
  resolveConstraintPath,
  resolveConstraintPaths,
  type PathToken,
  type ResolveContext,
} from "../src/lib/constraintXPath";
import {
  bookElement,
  bookKeyConstraint,
  bookRefParticleElement,
  constraintsModel,
  contactHolderElement,
  danglingRefConstraint,
  editionElement,
  isbnElement,
  libraryElement,
  loanBookRefConstraint,
  loanElement,
  nodeRootElement,
  publisherElement,
  recursiveHolderElement,
  recursiveMarkerElement,
  refHolderElement,
  titleAttr,
  uniqueTitleConstraint,
} from "./fixtures/constraintsModel";

function ctxFor(model = constraintsModel): ResolveContext {
  const { index, indexById } = buildIndex(model);
  return { index, indexById };
}

function text(tokens: PathToken[]): string {
  return tokens.map((t) => t.text).join("");
}

describe("resolveConstraintPath", () => {
  const ctx = ctxFor();

  it("resolves a plain multi-step path", () => {
    const tokens = resolveConstraintPath("tns:Books/tns:Book", libraryElement, ctx);
    expect(text(tokens)).toBe("tns:Books/tns:Book");
    const steps = tokens.filter((t) => t.kind === "step");
    expect(steps).toHaveLength(2);
    expect(steps[0].targetId).not.toBeNull();
    expect(steps[1].targetId).toBe(bookElement.id);
    expect(steps[1].targetKind).toBe("element");
    const seps = tokens.filter((t) => t.kind === "sep");
    expect(seps).toHaveLength(1);
    expect(seps[0].text).toBe("/");
  });

  it("ignores namespace prefixes and matches on local name", () => {
    const withPrefix = resolveConstraintPath("tns:Books/tns:Book", libraryElement, ctx);
    const withoutPrefix = resolveConstraintPath("Books/Book", libraryElement, ctx);
    expect(withPrefix.at(-1)!.targetId).toBe(bookElement.id);
    expect(withoutPrefix.at(-1)!.targetId).toBe(bookElement.id);
  });

  it("resolves a step reached through a group ref (BookCore holds ISBN)", () => {
    const tokens = resolveConstraintPath("tns:ISBN", bookElement, ctx);
    expect(tokens).toHaveLength(1);
    expect(tokens[0].targetId).toBe(isbnElement.id);
    expect(tokens[0].targetKind).toBe("element");
  });

  it("resolves a step reached through an extension base with no own particle (SpecialBookType)", () => {
    const specialBook = { ...bookElement, id: "element:test:special", type_name: "tns:SpecialBookType" };
    const tokens = resolveConstraintPath("tns:ISBN", specialBook, ctx);
    expect(tokens[0].targetId).toBe(isbnElement.id);
  });

  it("interleaves base-then-own children when the extension also adds its own element", () => {
    const extended = { ...bookElement, id: "element:test:extended", type_name: "tns:ExtendedBookType" };
    const children = collectChildElements(extended, ctx);
    expect(children.map((c) => c.name)).toEqual(["ISBN", "Edition", "Publisher"]);
    expect(children[2].id).toBe(publisherElement.id);
  });

  it("resolves an attribute step written as @name", () => {
    const tokens = resolveConstraintPath("@title", bookElement, ctx);
    expect(tokens).toHaveLength(1);
    expect(tokens[0].kind).toBe("attr");
    expect(tokens[0].targetId).toBe(titleAttr.id);
    expect(tokens[0].targetKind).toBe("attribute");
  });

  it("resolves an attribute step written as attribute::name", () => {
    const tokens = resolveConstraintPath("attribute::title", bookElement, ctx);
    expect(text(tokens)).toBe("attribute::title");
    expect(tokens[0].kind).toBe("attr");
    expect(tokens[0].targetId).toBe(titleAttr.id);
  });

  it("resolves a step written as child::name", () => {
    const tokens = resolveConstraintPath("child::tns:Book", libraryElement, ctx);
    expect(text(tokens)).toBe("child::tns:Book");
    // "Book" is not a direct child of Library — this exercises the
    // child:: syntax against a context where it *is* a direct child.
    const booksThenBook = resolveConstraintPath("tns:Books/child::tns:Book", libraryElement, ctx);
    expect(booksThenBook.at(-1)!.targetId).toBe(bookElement.id);
  });

  it("performs a descendant BFS search for .//", () => {
    const tokens = resolveConstraintPath(".//tns:Book", libraryElement, ctx);
    expect(text(tokens)).toBe(".//tns:Book");
    const sep = tokens.find((t) => t.text === ".//");
    expect(sep?.kind).toBe("sep");
    expect(tokens.at(-1)!.targetId).toBe(bookElement.id);
  });

  it("resolves a union of paths, preserving verbatim separator whitespace", () => {
    const raw = "tns:Books/tns:Book | tns:Loans/tns:Loan";
    const tokens = resolveConstraintPath(raw, libraryElement, ctx);
    expect(text(tokens)).toBe(raw);
    const sep = tokens.find((t) => t.kind === "sep" && t.text.includes("|"));
    expect(sep?.text).toBe(" | ");
    expect(tokens.at(-1)!.targetId).toBe(loanElement.id);
    const firstAlternativeLast = tokens.find((t) => t.targetId === bookElement.id);
    expect(firstAlternativeLast).toBeDefined();
  });

  it("leaves an unresolvable step and everything after it as plain text", () => {
    const tokens = resolveConstraintPath("tns:Books/tns:NoSuchElement/tns:Foo", libraryElement, ctx);
    expect(text(tokens)).toBe("tns:Books/tns:NoSuchElement/tns:Foo");
    const steps = tokens.filter((t) => t.kind === "step");
    expect(steps[0].targetId).not.toBeNull(); // Books
    expect(steps[1].targetId).toBeNull(); // NoSuchElement
    expect(steps[2].targetId).toBeNull(); // Foo — tail stays plain too
  });

  it("treats * as an unresolvable wildcard step and cuts off further context", () => {
    const tokens = resolveConstraintPath("tns:Books/*/tns:Book", libraryElement, ctx);
    const steps = tokens.filter((t) => t.kind === "step");
    expect(steps[0].targetId).not.toBeNull(); // Books
    expect(steps[1].text).toBe("*");
    expect(steps[1].targetId).toBeNull();
    expect(steps[2].targetId).toBeNull(); // Book after * stays unresolved
  });

  it("resolves '.' to the current context node itself", () => {
    const tokens = resolveConstraintPath(".", bookElement, ctx);
    expect(tokens).toHaveLength(1);
    expect(tokens[0].kind).toBe("step");
    expect(tokens[0].targetId).toBe(bookElement.id);
    expect(tokens[0].targetKind).toBe("element");
  });

  it("follows an element ref particle to its target's children, keeping the ref's own id as targetId", () => {
    const tokens = resolveConstraintPath("tns:Book/tns:ISBN", refHolderElement, ctx);
    expect(tokens[0].targetId).toBe(bookRefParticleElement.id);
    expect(tokens[0].targetId).not.toBe(bookElement.id);
    expect(tokens.at(-1)!.targetId).toBe(isbnElement.id);
  });

  it("does not infinite-loop on a self-referencing group ref (recursion cap)", () => {
    const children = collectChildElements(recursiveHolderElement, ctx);
    expect(children.map((c) => c.name)).toEqual(["Marker"]);
    expect(children[0].id).toBe(recursiveMarkerElement.id);
  });

  it("terminates the .// BFS over a self-recursive element type without hanging", () => {
    const tokens = resolveConstraintPath(".//tns:NoSuchThing", nodeRootElement, ctx);
    expect(tokens.at(-1)!.targetId).toBeNull();
  });

  it("finds a genuinely nested descendant within the recursion cap", () => {
    const tokens = resolveConstraintPath(".//tns:Value", nodeRootElement, ctx);
    expect(tokens.at(-1)!.targetId).not.toBeNull();
  });
});

describe("collectChildElements", () => {
  const ctx = ctxFor();

  it("flattens a group ref inline with the type's own elements", () => {
    const children = collectChildElements(bookElement, ctx);
    expect(children.map((c) => c.name)).toEqual(["ISBN", "Edition"]);
  });

  it("returns [] for an element with no complex type", () => {
    const children = collectChildElements(isbnElement, ctx);
    expect(children).toEqual([]);
  });
});

describe("collectAttributes", () => {
  const ctx = ctxFor();

  it("collects an attribute declared directly on the type", () => {
    const attrs = collectAttributes(bookElement, ctx);
    expect(attrs.map((a) => a.name)).toContain("title");
  });

  it("collects attributes contributed via an attribute-group ref", () => {
    const attrs = collectAttributes(contactHolderElement, ctx);
    expect(attrs.map((a) => a.name)).toEqual(["phone"]);
  });
});

describe("resolveConstraintPaths", () => {
  const ctx = ctxFor();

  it("resolves fields relative to the first selector target (key on Books/Book)", () => {
    const result = resolveConstraintPaths(bookKeyConstraint, libraryElement, ctx);
    expect(result.selectorTargets).toHaveLength(1);
    expect(result.selectorTargets[0].id).toBe(bookElement.id);
    expect(result.fields).toHaveLength(1);
    expect(result.fields[0].at(-1)!.targetId).toBe(isbnElement.id);
  });

  it("resolves an attribute field (@title) and an element field (Edition) via .// selector", () => {
    const result = resolveConstraintPaths(uniqueTitleConstraint, libraryElement, ctx);
    expect(result.selectorTargets[0].id).toBe(bookElement.id);
    expect(result.fields[0][0].targetId).toBe(titleAttr.id);
    expect(result.fields[0][0].kind).toBe("attr");
    expect(result.fields[1][0].targetId).toBe(editionElement.id);
  });

  it("resolves a keyref selector independent of its refer target", () => {
    const result = resolveConstraintPaths(loanBookRefConstraint, libraryElement, ctx);
    expect(result.selectorTargets[0].id).toBe(loanElement.id);
    expect(result.fields[0].at(-1)!.targetId).not.toBeNull();
  });

  it("leaves fields unresolved when the selector itself never resolves", () => {
    const result = resolveConstraintPaths(danglingRefConstraint, libraryElement, ctx);
    // selector "tns:Loans/tns:Loan" still resolves fine on its own — refer_id
    // being dangling is orthogonal — so assert on a genuinely-broken one
    // built from an existing constraint's shape instead.
    expect(result.selectorTargets[0].id).toBe(loanElement.id);
    const broken = resolveConstraintPaths(
      { ...danglingRefConstraint, selector: "tns:NoSuchChild" },
      libraryElement,
      ctx,
    );
    expect(broken.selectorTargets).toHaveLength(0);
    expect(broken.fields[0][0].targetId).toBeNull();
  });
});
