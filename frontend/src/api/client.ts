import type { SchemaResponse } from "../types/schema";

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

export function exportHtmlUrl(schemaId: string): string {
  return `${API_BASE}/schema/${schemaId}/export/html`;
}

export function exportFormattedFileUrl(schemaId: string, fileId: string): string {
  return `${API_BASE}/schema/${schemaId}/file/${fileId}/formatted`;
}
