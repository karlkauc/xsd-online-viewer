/** Classify backend parse errors so the UI can show an actionable hint. */

export const XML_VIEWER_URL = "https://www.xml-viewer.online/";

export type UploadErrorKind =
  | "xml-document"
  | "schema-namespace"
  | "binary-file"
  | "not-xml"
  | "zip-no-xsd"
  | "dtd"
  | "too-large"
  | "rate-limit"
  | "unknown";

export interface ClassifiedError {
  kind: UploadErrorKind;
  title: string;
  message: string;
}

const RULES: Array<[RegExp, UploadErrorKind, string]> = [
  // Must precede the xml-document rule: this root *is* a schema, only its xmlns is off.
  [/the root element <schema>/i, "schema-namespace", "The schema's XML namespace is missing or wrong"],
  [/not <xs:schema>|looks like an XML document|root element is not xs:schema/i, "xml-document", "This is an XML document, not an XML Schema"],
  [/not an XML file.*binary/i, "binary-file", "This is a binary file, not a schema"],
  [/not an XML file|Start tag expected|the file is empty/i, "not-xml", "The file is not XML"],
  [/ZIP archive contains no/i, "zip-no-xsd", "The ZIP contains no schema"],
  [/DTD construct/i, "dtd", "The schema uses DTD declarations we cannot accept"],
  [/exceeds .* MB limit|HTTP 413/i, "too-large", "The file is too large"],
  [/rate.?limit|HTTP 429|^limit: \d+ per/i, "rate-limit", "Too many requests"],
];

export function classifyUploadError(message: string): ClassifiedError {
  for (const [pattern, kind, title] of RULES) {
    if (pattern.test(message)) return { kind, title, message };
  }
  return { kind: "unknown", title: "Could not load the schema", message };
}

const SCHEMA_ROOT_RE = /<(?:[A-Za-z_][\w.-]*:)?schema[\s>/]/;

/**
 * Cheap client-side check for files named `.xml`: if the first bytes show no
 * `<…:schema` root, it is almost certainly an XML document and uploading it
 * (often several MB) would only yield a 400.
 */
export function looksLikeSchema(head: string): boolean {
  return SCHEMA_ROOT_RE.test(head);
}

export function shouldSniff(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return lower.endsWith(".xml") && !lower.endsWith(".xsd");
}
