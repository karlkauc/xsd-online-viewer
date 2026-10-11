import { describe, expect, it } from "vitest";
import { completeWildcard, sameWildcard } from "../src/lib/wildcards";
import type { Wildcard } from "../src/types/schema";

function wildcard(
  namespace: string | null,
  extra: Partial<Wildcard> = {},
): Wildcard {
  return {
    namespace,
    not_namespace: null,
    not_qname: null,
    process_contents: "lax",
    annotation: null,
    ...extra,
  };
}

const T = "urn:t";

describe("completeWildcard", () => {
  it("is the type's own wildcard when nothing else is involved", () => {
    const own = wildcard("##other");
    expect(sameWildcard(completeWildcard([{ wildcard: own, target: T }], null, T), own)).toBe(true);
    expect(completeWildcard([], null, T)).toBeNull();
  });

  it("intersects the own wildcard with those of the attribute groups", () => {
    const result = completeWildcard(
      [
        { wildcard: wildcard("urn:a urn:b ##local", { process_contents: "skip" }), target: T },
        { wildcard: wildcard("urn:b urn:c ##local"), target: T },
      ],
      null,
      T,
    );
    expect(result?.namespace).toBe("urn:b ##local");
    // The first one — the type's own — decides how matches are processed.
    expect(result?.process_contents).toBe("skip");
  });

  it("takes excluded namespaces out of a list", () => {
    const result = completeWildcard(
      [
        { wildcard: wildcard("urn:a urn:b"), target: T },
        { wildcard: wildcard(null, { not_namespace: "urn:a" }), target: T },
      ],
      null,
      T,
    );
    expect(result?.namespace).toBe("urn:b");
  });

  it("admits nothing when the wildcards have nothing in common", () => {
    expect(
      completeWildcard(
        [
          { wildcard: wildcard("urn:a"), target: T },
          { wildcard: wildcard("urn:b"), target: T },
        ],
        null,
        T,
      ),
    ).toBeNull();
  });

  it("unites an extension's wildcard with the base type's", () => {
    const result = completeWildcard(
      [{ wildcard: wildcard("urn:a"), target: T }],
      { wildcard: wildcard("##targetNamespace urn:b"), target: T },
      T,
    );
    expect(result?.namespace?.split(" ").sort()).toEqual(["##targetNamespace", "urn:a", "urn:b"]);
  });

  it("widens ##other by what the other side lists", () => {
    // ##other leaves out the target namespace and no namespace; the base adds the first back.
    const result = completeWildcard(
      [{ wildcard: wildcard("##other"), target: T }],
      { wildcard: wildcard("##targetNamespace"), target: T },
      T,
    );
    expect(result?.namespace).toBeNull();
    expect(result?.not_namespace).toBe("##local");
    // And both together admit everything.
    const all = completeWildcard(
      [{ wildcard: wildcard("##other"), target: T }],
      { wildcard: wildcard("##targetNamespace ##local"), target: T },
      T,
    );
    expect(all?.namespace).toBeNull();
    expect(all?.not_namespace).toBeNull();
  });

  it("reads ##targetNamespace against the file each wildcard sits in", () => {
    const result = completeWildcard(
      [{ wildcard: wildcard("##targetNamespace"), target: "urn:derived" }],
      { wildcard: wildcard("##targetNamespace"), target: "urn:base" },
      "urn:derived",
    );
    expect(result?.namespace).toBe("##targetNamespace urn:base");
  });

  it("inherits the base wildcard when the extension has none", () => {
    const base = wildcard("##any", { process_contents: "strict" });
    expect(completeWildcard([], { wildcard: base, target: T }, T)).toBe(base);
  });

  it("keeps a notQName only where every side rules the name out", () => {
    const own = wildcard("##any", { not_qname: "t:a t:b" });
    const group = wildcard("##any", { not_qname: "t:c" });
    const intersected = completeWildcard(
      [
        { wildcard: own, target: T },
        { wildcard: group, target: T },
      ],
      null,
      T,
    );
    expect(intersected?.not_qname).toBe("t:a t:b t:c");
    const united = completeWildcard(
      [{ wildcard: own, target: T }],
      { wildcard: wildcard("##any", { not_qname: "t:b" }), target: T },
      T,
    );
    expect(united?.not_qname).toBe("t:b");
  });
});
