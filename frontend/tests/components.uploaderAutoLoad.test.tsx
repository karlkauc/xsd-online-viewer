import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Uploader } from "../src/components/Uploader";
import * as client from "../src/api/client";
import { useSelection } from "../src/stores/selectionStore";
import type { SchemaModel } from "../src/types/schema";

const EMPTY_MODEL = {
  schema_id: "x",
  target_namespace: null,
  namespaces: {},
  element_form_default: "unqualified",
  attribute_form_default: "unqualified",
  elements: [],
  attributes: [],
  simple_types: [],
  complex_types: [],
  groups: [],
  attribute_groups: [],
  files: [],
  diagnostics: [],
  xsd_version: "unknown",
  overrides: [],
} as unknown as SchemaModel;

describe("Uploader auto-load from a shared link", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useSelection.getState().clearSchema();
    window.history.replaceState(null, "", "/");
  });

  it("loads /url?src=… on mount and keeps the source in the store", async () => {
    const spy = vi
      .spyOn(client, "loadSchemaFromUrl")
      .mockResolvedValue({ schema_id: "s1", model: EMPTY_MODEL });
    window.history.replaceState(null, "", "/url?src=https%3A%2F%2Fexample.com%2Fx.xsd#/id/element%3AA");
    render(<Uploader />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith("https://example.com/x.xsd"));
    await waitFor(() => expect(useSelection.getState().schemaId).toBe("s1"));
    expect(useSelection.getState().source).toEqual({ kind: "url", url: "https://example.com/x.xsd" });
    expect(window.location.pathname + window.location.search).toBe(
      "/url?src=https%3A%2F%2Fexample.com%2Fx.xsd",
    );
    expect(window.location.hash).toBe("#/id/element%3AA");
  });

  it("loads /fundsxml?release=…&file=… on mount", async () => {
    const spy = vi
      .spyOn(client, "loadSchemaFromRelease")
      .mockResolvedValue({ schema_id: "s2", model: EMPTY_MODEL });
    window.history.replaceState(null, "", "/fundsxml?release=4.2.11&file=FundsXML4.xsd");
    render(<Uploader />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith("4.2.11", "FundsXML4.xsd"));
  });

  it("does nothing without parameters", () => {
    const spy = vi.spyOn(client, "loadSchemaFromUrl");
    window.history.replaceState(null, "", "/url");
    render(<Uploader />);
    expect(spy).not.toHaveBeenCalled();
  });
});
