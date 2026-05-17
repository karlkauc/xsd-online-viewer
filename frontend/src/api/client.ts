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

export async function uploadSchemaFile(
  file: File,
  mainFilename?: string,
): Promise<SchemaResponse> {
  const form = new FormData();
  form.append("file", file);
  if (mainFilename) form.append("main_filename", mainFilename);
  const response = await fetch(`${API_BASE}/schema/upload`, {
    method: "POST",
    body: form,
  });
  return handle(response);
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

export async function validateXmlText(
  schemaId: string,
  content: string,
  filename = "document.xml",
): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE}/schema/${schemaId}/validate/text`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, filename }),
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

export function exportHtmlUrl(schemaId: string): string {
  return `${API_BASE}/schema/${schemaId}/export/html`;
}

export function exportFormattedFileUrl(schemaId: string, fileId: string): string {
  return `${API_BASE}/schema/${schemaId}/file/${fileId}/formatted`;
}
