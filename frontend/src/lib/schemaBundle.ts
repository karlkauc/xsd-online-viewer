import { ApiError } from "../api/client";
import { withSchemaRetry } from "./schemaSession";
import type { HandoffSchema } from "./xmlViewerHandoff";

export function exportBundleUrl(schemaId: string): string {
  return `/api/schema/${schemaId}/export/bundle`;
}

function filenameFromDisposition(header: string | null): string | null {
  const match = header?.match(/filename="([^"]+)"/);
  return match ? match[1] : null;
}

/** The loaded schema as one downloadable file (single .xsd or ZIP of all files). */
export async function fetchSchemaBundle(): Promise<HandoffSchema> {
  return withSchemaRetry(async (schemaId) => {
    const response = await fetch(exportBundleUrl(schemaId));
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // keep the status line
      }
      throw new ApiError(detail, response.status);
    }
    const content = await response.arrayBuffer();
    const name = filenameFromDisposition(response.headers.get("content-disposition")) ?? "schema.xsd";
    const mainFilename = response.headers.get("x-main-filename") ?? undefined;
    return name.endsWith(".zip") ? { name, content, mainFilename } : { name, content };
  });
}
