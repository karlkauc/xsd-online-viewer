/**
 * Calls that need the schema on the server. The parsed model lives in the
 * browser, but validation, exports and sample generation address the
 * server-side cache by `schema_id`, which expires after an hour of disuse and
 * is per-instance on Cloud Run. When the server says the schema is gone we
 * re-submit the original source — the id is a hash of the model, so it comes
 * back unchanged — and retry the call. Twice at most: the reload and the
 * retry can land on different instances.
 */
import { ApiError } from "../api/client";
import { useSelection } from "../stores/selectionStore";
import { reloadSource } from "./schemaSource";

/** The backend's 404 detail for an unknown schema id (`api/export.py`, `api/schema.py`). */
const SCHEMA_EXPIRED = "schema not found or expired";
const MAX_RELOADS = 2;

export class SchemaExpiredError extends Error {
  constructor() {
    super("The schema has expired on the server. Please load it again.");
  }
}

// Other 404s ("element not found in schema") are answers, not expiry.
function isExpiry(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404 && err.message === SCHEMA_EXPIRED;
}

export async function withSchemaRetry<T>(fn: (schemaId: string) => Promise<T>): Promise<T> {
  const { schemaId, source, setSchemaId } = useSelection.getState();
  if (!schemaId) throw new SchemaExpiredError();
  let current = schemaId;
  for (let reloads = 0; ; reloads++) {
    try {
      return await fn(current);
    } catch (err) {
      if (!isExpiry(err) || !source) throw err;
      if (reloads === MAX_RELOADS) throw new SchemaExpiredError();
    }
    try {
      current = (await reloadSource(source)).schema_id;
    } catch {
      throw new SchemaExpiredError();
    }
    if (current !== useSelection.getState().schemaId) setSchemaId(current);
  }
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
