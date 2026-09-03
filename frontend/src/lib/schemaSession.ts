/**
 * Calls that need the schema on the server. The parsed model lives in the
 * browser, but validation, exports and sample generation address the
 * server-side cache by `schema_id`, which expires after an hour and is
 * per-instance on Cloud Run. On a 404 we re-submit the original source
 * once — the id is a hash of the model, so it comes back unchanged — and
 * retry the call.
 */
import { ApiError } from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { reloadSource } from "./schemaSource";

export class SchemaExpiredError extends Error {
  constructor() {
    super("The schema has expired on the server. Please load it again.");
  }
}

export async function withSchemaRetry<T>(fn: (schemaId: string) => Promise<T>): Promise<T> {
  const { schemaId, source, setSchemaId } = useSelection.getState();
  if (!schemaId) throw new SchemaExpiredError();
  try {
    return await fn(schemaId);
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 404 || !source) throw err;
  }
  let renewed: string;
  try {
    const response = await reloadSource(source);
    renewed = response.schema_id;
  } catch {
    throw new SchemaExpiredError();
  }
  if (renewed !== schemaId) setSchemaId(renewed);
  return fn(renewed);
}

/** Fetch a server-side export (with the retry above) and save it as a file. */
export async function downloadSchemaExport(
  pathFor: (schemaId: string) => string,
  filename: string,
): Promise<void> {
  const blob = await withSchemaRetry(async (schemaId) => {
    const response = await fetch(pathFor(schemaId));
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // fall back to the status line
      }
      throw new ApiError(detail, response.status);
    }
    return response.blob();
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
