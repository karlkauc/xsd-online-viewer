import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import * as client from "../src/api/client";
import { SchemaExpiredError, withSchemaRetry } from "../src/lib/schemaSession";
import { useSelection } from "../src/stores/selectionStore";

beforeEach(() => {
  useSelection.setState({ schemaId: "old", source: { kind: "text", content: "<xs:schema/>" } });
});
afterEach(() => vi.restoreAllMocks());

describe("withSchemaRetry", () => {
  it("returns the result directly when the call succeeds", async () => {
    const fn = vi.fn().mockResolvedValue("ok");
    await expect(withSchemaRetry(fn)).resolves.toBe("ok");
    expect(fn).toHaveBeenCalledWith("old");
  });

  it("re-submits the source once on 404 and retries with the renewed id", async () => {
    const reload = vi
      .spyOn(client, "uploadSchemaText")
      .mockResolvedValue({ schema_id: "new", model: {} as never });
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("schema not found or expired", 404))
      .mockResolvedValueOnce("ok");
    await expect(withSchemaRetry(fn)).resolves.toBe("ok");
    expect(reload).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenNthCalledWith(2, "new");
    expect(useSelection.getState().schemaId).toBe("new");
  });

  it("passes other errors through untouched and gives up when the reload fails", async () => {
    const boom = new ApiError("bad request", 400);
    await expect(withSchemaRetry(vi.fn().mockRejectedValue(boom))).rejects.toBe(boom);

    vi.spyOn(client, "uploadSchemaText").mockRejectedValue(new ApiError("nope", 500));
    const fn = vi.fn().mockRejectedValue(new ApiError("expired", 404));
    await expect(withSchemaRetry(fn)).rejects.toBeInstanceOf(SchemaExpiredError);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
