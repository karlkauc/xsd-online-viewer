import type { SchemaCheckResponse, SchemaResponse, ValidationResponse } from "../types/schema";

const API_BASE = "/api";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

// A 403/407 without our JSON error body never came from this app (it has no
// such responses): a corporate proxy, firewall or WAF refused the request.
// Saying so beats a bare "HTTP 403" (GitHub issue #1).
const BLOCKED_STATUSES = new Set([403, 407]);

export function blockedMessage(status: number): string {
  return (
    `The request was blocked before it reached the XSD Viewer (HTTP ${status}). ` +
    "A proxy, firewall or security filter on your network probably refused it — " +
    "try another network, or run the viewer yourself with Docker (see the GitHub README)."
  );
}

/** ApiError for a failed response: the backend's `detail`, or what the status means. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let detail: string | null = null;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // not our JSON: an intermediary answered, or the body was empty
  }
  if (detail === null) detail = BLOCKED_STATUSES.has(response.status) ? blockedMessage(response.status) : `HTTP ${response.status}`;
  return new ApiError(detail, response.status);
}

async function handle(response: Response): Promise<SchemaResponse> {
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as SchemaResponse;
}

/**
 * Upload one `.xsd`/`.zip`, or several loose schema files that include or
 * import each other by file name. `mainFilename` names the root schema (a
 * ZIP entry path or one of the file names); omitted, the backend guesses.
 */
export async function uploadSchemaFiles(
  files: File[],
  mainFilename?: string,
): Promise<SchemaResponse> {
  const form = new FormData();
  for (const file of files) form.append("file", file);
  if (mainFilename) form.append("main_filename", mainFilename);
  const response = await fetch(`${API_BASE}/schema/upload`, {
    method: "POST",
    body: form,
  });
  return handle(response);
}

export function uploadSchemaFile(file: File, mainFilename?: string): Promise<SchemaResponse> {
  return uploadSchemaFiles([file], mainFilename);
}

export async function uploadSchemaText(
  content: string,
  filename = "schema.xsd",
): Promise<SchemaResponse> {
  const response = await fetch(`${API_BASE}/schema/text`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, filename }),
  });
  return handle(response);
}

export async function loadSchemaFromUrl(url: string): Promise<SchemaResponse> {
  const response = await fetch(`${API_BASE}/schema/url`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return handle(response);
}

export interface FundsXmlAsset {
  filename: string;
  download_url: string;
  size: number;
  content_type: string | null;
}

export interface FundsXmlRelease {
  tag_name: string;
  name: string | null;
  published_at: string;
  prerelease: boolean;
  html_url: string;
  assets: FundsXmlAsset[];
}

export interface FundsXmlReleasesResponse {
  releases: FundsXmlRelease[];
  cached_at: string;
  ttl_seconds: number;
}

export async function loadSchemaFromRelease(
  tagName: string,
  mainFilename: string,
): Promise<SchemaResponse> {
  const response = await fetch(
    `${API_BASE}/fundsxml/releases/${encodeURIComponent(tagName)}/load`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ main_filename: mainFilename }),
    },
  );
  return handle(response);
}

export async function listFundsXmlReleases(): Promise<FundsXmlReleasesResponse> {
  const response = await fetch(`${API_BASE}/fundsxml/releases`);
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as FundsXmlReleasesResponse;
}

async function handleJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as T;
}

/**
 * The XSD version to validate as, when the caller says so. Left out, the
 * backend goes by what the schema's syntax suggests — which says nothing for
 * a schema that reads the same in both versions and means something else.
 */
export type XsdVersionChoice = "1.0" | "1.1";

function versionQuery(xsdVersion: XsdVersionChoice | undefined): string {
  return xsdVersion ? `?xsd_version=${xsdVersion}` : "";
}

export async function validateXmlFile(
  schemaId: string,
  file: File,
  xsdVersion?: XsdVersionChoice,
): Promise<ValidationResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(
    `${API_BASE}/schema/${schemaId}/validate/upload${versionQuery(xsdVersion)}`,
    { method: "POST", body: form },
  );
  return handleJson<ValidationResponse>(response);
}

/** Where the XML came from; recorded as the usage event's `source`. */
export type ValidateTextOrigin = "text" | "sample";

/**
 * How a generated sample was produced. Sent back with the sample's validation
 * request so the backend can record *why* a sample came out wrong — see
 * backend/app/usage/sample_issue.py. Diagnostics only; it never changes the
 * validation result.
 */
export interface SampleContext {
  element_id: string;
  element_qname?: string | null;
  include_optional: boolean;
  repeat?: number;
  max_depth?: number;
  generation_ms?: number | null;
  /** Opaque `X-Sample-Report` value, passed through untouched. */
  report?: string | null;
}

export async function validateXmlText(
  schemaId: string,
  content: string,
  filename = "document.xml",
  origin: ValidateTextOrigin = "text",
  sample?: SampleContext,
  xsdVersion?: XsdVersionChoice,
): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE}/schema/${schemaId}/validate/text${versionQuery(xsdVersion)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, filename, origin, sample: sample ?? null }),
  });
  return handleJson<ValidationResponse>(response);
}

export async function validateXmlUrl(
  schemaId: string,
  url: string,
  xsdVersion?: XsdVersionChoice,
): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE}/schema/${schemaId}/validate/url${versionQuery(xsdVersion)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return handleJson<ValidationResponse>(response);
}

export interface SampleXmlOptions {
  includeOptional?: boolean;
  repeat?: number;
}

/** Declarations a schema references but never loaded; such a schema cannot compile. */
export interface MissingReferences {
  count: number;
  /** The first few, for display. */
  names: string[];
}

export interface SampleXmlResult {
  xml: string;
  /** Opaque generator report; forwarded to `validateXmlText`, never parsed here. */
  report: string | null;
  generationMs: number;
  /** Set when the sample hit references the loaded files do not define. */
  missing: MissingReferences | null;
}

/** `X-Sample-Missing`: percent-encoded JSON. Anything malformed counts as complete. */
function parseMissingReferences(raw: string | null): MissingReferences | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(decodeURIComponent(raw));
    if (typeof parsed?.count !== "number" || parsed.count <= 0 || !Array.isArray(parsed.names)) return null;
    return { count: parsed.count, names: parsed.names.filter((n: unknown): n is string => typeof n === "string") };
  } catch {
    return null;
  }
}

/**
 * What a second validator finds wrong with the schema itself. Advisory: null
 * when the check is unavailable, so a failure never gets in the viewer's way.
 * A large schema is only checked when `large` asks for it, which takes a while.
 */
export async function fetchSchemaCheck(
  schemaId: string,
  large = false,
): Promise<SchemaCheckResponse | null> {
  try {
    const response = await fetch(`${API_BASE}/schema/${schemaId}/check${large ? "?large=true" : ""}`);
    if (!response.ok) return null;
    return (await response.json()) as SchemaCheckResponse;
  } catch {
    return null;
  }
}

/** Skeleton instance document rooted at `elementId`, as pretty-printed XML text. */
export async function fetchSampleXml(
  schemaId: string,
  elementId: string,
  options: SampleXmlOptions = {},
): Promise<SampleXmlResult> {
  const started = performance.now();
  const params = new URLSearchParams({ element: elementId });
  if (options.includeOptional) params.set("optional", "true");
  if (options.repeat && options.repeat > 1) params.set("repeat", String(options.repeat));
  const response = await fetch(`${API_BASE}/schema/${schemaId}/sample?${params.toString()}`);
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return {
    xml: await response.text(),
    report: response.headers.get("X-Sample-Report"),
    generationMs: Math.round(performance.now() - started),
    missing: parseMissingReferences(response.headers.get("X-Sample-Missing")),
  };
}

export function exportHtmlUrl(schemaId: string): string {
  return `${API_BASE}/schema/${schemaId}/export/html`;
}

export function exportFormattedFileUrl(schemaId: string, fileId: string): string {
  return `${API_BASE}/schema/${schemaId}/file/${fileId}/formatted`;
}

export interface FeedbackPayload {
  message: string;
  email?: string;
  page?: string;
  schema_name?: string;
  error_detail?: string;
  /** Honeypot — must stay empty; bots that fill it are dropped server-side. */
  website?: string;
}

export async function sendFeedback(payload: FeedbackPayload): Promise<void> {
  const response = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}

export interface HealthResponse {
  status: string;
  version: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as HealthResponse;
}

/** Count a copied share link (the copy itself never reaches the server). Fire and forget. */
export function pingShare(source: "url" | "fundsxml" | "iso20022"): void {
  void fetch(`${API_BASE}/usage/share?source=${source}`, { method: "POST", keepalive: true }).catch(() => undefined);
}

/** Browser-only features counted by `POST /api/usage/feature` (F1). Keep in sync with
 * `FEATURE_NAMES` in backend/app/api/usage.py: the server rejects any other name. */
export type FeatureName = "diagram_png" | "diagram_svg" | "search_open";

const pingedFeatures = new Set<FeatureName>();

/** Count the use of a browser-only feature. Fire-and-forget like {@link pingShare}, never
 * throws; with `once` at most one ping per page load (the search palette opens often). */
export function pingFeature(name: FeatureName, { once = false }: { once?: boolean } = {}): void {
  if (once) {
    if (pingedFeatures.has(name)) return;
    pingedFeatures.add(name);
  }
  try {
    void fetch(`${API_BASE}/usage/feature?name=${name}`, { method: "POST", keepalive: true }).catch(() => undefined);
  } catch {
    // No fetch at all (very old browser): statistics are optional.
  }
}

let contentPages: Promise<Set<string>> | null = null;

/** Slugs of the server-rendered pages (/fundsxml/4.2.11, /features/diagram …), fetched once. */
export function fetchContentPages(): Promise<Set<string>> {
  contentPages ??= fetch(`${API_BASE}/content/pages`)
    .then((r) => (r.ok ? (r.json() as Promise<string[]>) : []))
    .then((slugs) => new Set(slugs))
    .catch(() => new Set<string>());
  return contentPages;
}

// --- ISO 20022 (pinned public mirror, backend/app/api/iso20022.py) ---------

export interface Iso20022Message {
  id: string;
  message: string;
  variant: string;
  version: string;
  area: string;
  area_label: string;
  name: string;
  root: string;
  path: string;
}

export interface Iso20022Catalog {
  source: { repo: string; commit: string; license: string; base_url: string; official: string };
  messages: Iso20022Message[];
}

export async function listIso20022Messages(): Promise<Iso20022Catalog> {
  const response = await fetch(`${API_BASE}/iso20022/messages`);
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as Iso20022Catalog;
}

export async function loadIso20022(id: string): Promise<SchemaResponse> {
  const response = await fetch(`${API_BASE}/iso20022/${encodeURIComponent(id)}/load`, { method: "POST" });
  return handle(response);
}
