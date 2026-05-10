// Catalog of XSD built-in types that exist only in XSD 1.1. Used by the
// type-reference renderer to flag a 1.1 type with a small badge.
//
// Names are accepted in both ``xs:`` prefixed form (the common authoring
// form) and the Clark form ``{http://www.w3.org/2001/XMLSchema}name`` that
// the parser produces internally.

const XSD_NS = "http://www.w3.org/2001/XMLSchema";

const ONE_ONE_LOCAL_NAMES = [
  "dateTimeStamp",
  "yearMonthDuration",
  "dayTimeDuration",
  "precisionDecimal",
  "error",
] as const;

export const BUILTIN_TYPES_1_1: ReadonlySet<string> = new Set([
  ...ONE_ONE_LOCAL_NAMES.map((n) => `xs:${n}`),
  ...ONE_ONE_LOCAL_NAMES.map((n) => `xsd:${n}`),
  ...ONE_ONE_LOCAL_NAMES.map((n) => `{${XSD_NS}}${n}`),
]);

export function isXsd11Builtin(typeName: string | null | undefined): boolean {
  if (!typeName) return false;
  return BUILTIN_TYPES_1_1.has(typeName);
}
