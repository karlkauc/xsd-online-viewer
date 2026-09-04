import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchSchemaBundle } from "../src/lib/schemaBundle";
import { useSelection } from "../src/stores/selectionStore";

const fetchMock = vi.fn();
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  useSelection.setState({ schemaId: "abc", source: { kind: "text", content: "<xs:schema/>" } });
});
afterEach(() => vi.unstubAllGlobals());

function response(headers: Record<string, string>, body: string) {
  return {
    ok: true,
    status: 200,
    headers: { get: (k: string) => headers[k.toLowerCase()] ?? null },
    arrayBuffer: async () => new TextEncoder().encode(body).buffer,
  };
}

describe("fetchSchemaBundle", () => {
  it("returns a single .xsd without a main-file hint", async () => {
    fetchMock.mockResolvedValue(
      response({ "content-disposition": 'attachment; filename="simple.xsd"', "x-main-filename": "simple.xsd" }, "<xs:schema/>"),
    );
    const bundle = await fetchSchemaBundle();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/schema/abc/export/bundle");
    expect(bundle.name).toBe("simple.xsd");
    expect(bundle.mainFilename).toBeUndefined();
    expect(new TextDecoder().decode(bundle.content)).toBe("<xs:schema/>");
  });

  it("keeps the main file name for a ZIP", async () => {
    fetchMock.mockResolvedValue(
      response(
        { "content-disposition": 'attachment; filename="library-bundle.zip"', "x-main-filename": "schemas/library.xsd" },
        "PK",
      ),
    );
    const bundle = await fetchSchemaBundle();
    expect(bundle).toMatchObject({ name: "library-bundle.zip", mainFilename: "schemas/library.xsd" });
  });
});
