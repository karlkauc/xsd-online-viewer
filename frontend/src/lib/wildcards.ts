// The attribute wildcard a complex type ends up with, per XSD: its own
// xs:anyAttribute intersected with those of the attribute groups it uses, and
// for an extension the union of that with the base type's.

import type { Wildcard } from "../types/schema";

// `null` stands for "no namespace" (##local).
type Namespace = string | null;

type Constraint =
  | { kind: "any" }
  | { kind: "in"; names: Set<Namespace> }
  | { kind: "not"; names: Set<Namespace> };

interface Parsed {
  constraint: Constraint;
  notQName: string[];
}

// Stands for the target namespace while the real one is not known.
export const TARGET_TOKEN = "##targetNamespace";

function tokens(value: string | null | undefined): string[] {
  return (value ?? "").split(/\s+/).filter(Boolean);
}

function resolveToken(token: string, target: Namespace | undefined): Namespace {
  if (token === "##local") return null;
  if (token === "##targetNamespace") return target === undefined ? TARGET_TOKEN : target;
  return token;
}

function parse(wildcard: Wildcard, target: Namespace | undefined): Parsed {
  const notQName = tokens(wildcard.not_qname);
  if (wildcard.not_namespace) {
    const names = new Set(tokens(wildcard.not_namespace).map((t) => resolveToken(t, target)));
    return { constraint: { kind: "not", names }, notQName };
  }
  const listed = tokens(wildcard.namespace);
  if (!listed.length || listed.includes("##any")) return { constraint: { kind: "any" }, notQName };
  if (listed.includes("##other")) {
    const names = new Set<Namespace>([resolveToken("##targetNamespace", target), null]);
    return { constraint: { kind: "not", names }, notQName };
  }
  return {
    constraint: { kind: "in", names: new Set(listed.map((t) => resolveToken(t, target))) },
    notQName,
  };
}

const minus = (a: Set<Namespace>, b: Set<Namespace>) => new Set([...a].filter((n) => !b.has(n)));
const both = (a: Set<Namespace>, b: Set<Namespace>) => new Set([...a].filter((n) => b.has(n)));
const either = (a: Set<Namespace>, b: Set<Namespace>) => new Set([...a, ...b]);

function union(a: Constraint, b: Constraint): Constraint {
  if (a.kind === "any" || b.kind === "any") return { kind: "any" };
  if (a.kind === "in" && b.kind === "in") return { kind: "in", names: either(a.names, b.names) };
  const names =
    a.kind === "not" && b.kind === "not"
      ? both(a.names, b.names)
      : a.kind === "not"
        ? minus(a.names, b.names)
        : minus(b.names, a.names);
  return names.size ? { kind: "not", names } : { kind: "any" };
}

function intersection(a: Constraint, b: Constraint): Constraint {
  if (a.kind === "any") return b;
  if (b.kind === "any") return a;
  if (a.kind === "in" && b.kind === "in") return { kind: "in", names: both(a.names, b.names) };
  if (a.kind === "not" && b.kind === "not") return { kind: "not", names: either(a.names, b.names) };
  return a.kind === "in"
    ? { kind: "in", names: minus(a.names, b.names) }
    : { kind: "in", names: minus(b.names, a.names) };
}

function spell(name: Namespace, target: Namespace | undefined): string {
  if (name === null) return "##local";
  if (name === TARGET_TOKEN || (target !== undefined && name === target)) return TARGET_TOKEN;
  return name;
}

function unparse(
  parsed: Parsed,
  processContents: Wildcard["process_contents"],
  target: Namespace | undefined,
): Wildcard | null {
  const { constraint } = parsed;
  let namespace: string | null = null;
  let notNamespace: string | null = null;
  if (constraint.kind === "in") {
    // A wildcard that admits no namespace at all admits nothing.
    if (!constraint.names.size) return null;
    namespace = [...constraint.names].map((n) => spell(n, target)).join(" ");
  } else if (constraint.kind === "not") {
    const spelled = [...constraint.names].map((n) => spell(n, target)).sort();
    if (spelled.join(" ") === `##local ${TARGET_TOKEN}`) namespace = "##other";
    else notNamespace = spelled.join(" ");
  }
  return {
    namespace,
    not_namespace: notNamespace,
    not_qname: parsed.notQName.length ? parsed.notQName.join(" ") : null,
    process_contents: processContents,
    annotation: null,
  };
}

export interface SourcedWildcard {
  wildcard: Wildcard;
  /** Target namespace of the file that declares it; undefined when unknown. */
  target?: Namespace;
}

/**
 * What several wildcards admit together: the intersection of `own` (a type's
 * xs:anyAttribute and those of its attribute groups — the first one decides
 * processContents), united with `base` (the base type's complete wildcard)
 * for an extension. `target` is the namespace the result is spelled against.
 */
export function completeWildcard(
  own: SourcedWildcard[],
  base: SourcedWildcard | null,
  target?: Namespace,
): Wildcard | null {
  let local: Parsed | null = null;
  for (const source of own) {
    const parsed = parse(source.wildcard, source.target);
    local = local
      ? {
          constraint: intersection(local.constraint, parsed.constraint),
          // A name either one rules out stays out.
          notQName: [...new Set([...local.notQName, ...parsed.notQName])],
        }
      : parsed;
  }
  const localWildcard = local ? unparse(local, own[0].wildcard.process_contents, target) : null;
  if (!base) return localWildcard;
  if (!local || !localWildcard) return base.wildcard;
  const inherited = parse(base.wildcard, base.target);
  return unparse(
    {
      constraint: union(local.constraint, inherited.constraint),
      // Only a name both rule out stays out.
      notQName: local.notQName.filter((name) => inherited.notQName.includes(name)),
    },
    own[0].wildcard.process_contents,
    target,
  );
}

export function sameWildcard(a: Wildcard | null, b: Wildcard | null): boolean {
  if (!a || !b) return a === b;
  return (
    (a.namespace ?? "##any") === (b.namespace ?? "##any") &&
    (a.not_namespace ?? "") === (b.not_namespace ?? "") &&
    (a.not_qname ?? "") === (b.not_qname ?? "") &&
    (a.process_contents ?? "strict") === (b.process_contents ?? "strict")
  );
}
