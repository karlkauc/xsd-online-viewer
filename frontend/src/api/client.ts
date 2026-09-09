import type { SchemaResponse, ValidationResponse } from "../types/schema";

const API_BASE = "/api";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function handle(response: Response): Promise<SchemaResponse> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore parse errors; fall back to status
    }
    throw new ApiError(detail, response.status);
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
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as FundsXmlReleasesResponse;
}

async function handleJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore parse errors; fall back to status
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export async function validateXmlFile(
  schemaId: string,
  file: File,
): Promise<ValidationResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(
    `${API_BASE}/schema/${schemaId}/validate/upload`,
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
): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE}/schema/${schemaId}/validate/text`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, filename, origin, sample: sample ?? null }),
  });
  return handleJson<ValidationResponse>(response);
}

export async function validateXmlUrl(
  schemaId: string,
  url: string,
): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE}/schema/${schemaId}/validate/url`, {
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

export interface SampleXmlResult {
  xml: string;
  /** Opaque generator report; forwarded to `validateXmlText`, never parsed here. */
  report: string | null;
  generationMs: number;
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
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore parse errors; fall back to status
    }
    throw new ApiError(detail, response.status);
  }
  return {
    xml: await response.text(),
    report: response.headers.get("X-Sample-Report"),
    generationMs: Math.round(performance.now() - started),
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
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, response.status);
  }
}

export interface HealthResponse {
  status: string;
  version: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new ApiError(`HTTP ${response.status}`, response.status);
  return (await response.json()) as HealthResponse;
}
