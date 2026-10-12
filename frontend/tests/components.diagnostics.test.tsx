import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { Diagnostics } from "../src/components/Diagnostics";
import { useSelection } from "../src/stores/selectionStore";
import type { SchemaCheckResponse } from "../src/types/schema";
import { alternativesModel } from "./fixtures/alternativesModel";

function check(overrides: Partial<SchemaCheckResponse> = {}): SchemaCheckResponse {
  return {
    schema_id: "s1",
    status: "findings",
    version: "1.0",
    findings: [
      {
        severity: "error",
        message: "the derived group is an illegal restriction",
        file_id: alternativesModel.files[0].id,
        line: 11,
      },
    ],
    more: 0,
    detail: null,
    ...overrides,
  };
}

describe("Diagnostics", () => {
  beforeEach(() => {
    act(() => {
      useSelection.getState().clearSchema();
      useSelection.getState().setSchema("s1", alternativesModel);
    });
  });

  it("stays away while there is nothing to say", () => {
    const { container } = render(<Diagnostics />);
    expect(container.firstChild).toBeNull();
    act(() => useSelection.getState().setSchemaCheck(check({ status: "ok", findings: [] })));
    expect(container.firstChild).toBeNull();
  });

  it("lists what the schema check found, with the XSD version it was read as", () => {
    render(<Diagnostics />);
    act(() => useSelection.getState().setSchemaCheck(check({ more: 3 })));
    expect(screen.getByText("4 diagnostics")).toBeInTheDocument();
    expect(screen.getByText(/breaks rules of XSD 1\.0/)).toBeInTheDocument();
    expect(screen.getByText("the derived group is an illegal restriction")).toBeInTheDocument();
    expect(screen.getByText("… and 3 more")).toBeInTheDocument();
  });

  it("jumps to the line a finding is about", async () => {
    render(<Diagnostics />);
    act(() => useSelection.getState().setSchemaCheck(check()));
    await userEvent.click(screen.getByTitle("Open in the Text tab"));
    expect(useSelection.getState().activeTab).toBe("text");
    expect(useSelection.getState().sourceJump).toEqual({
      file_id: alternativesModel.files[0].id,
      line: 11,
    });
  });

  it("ignores an answer for a schema that is no longer loaded", () => {
    render(<Diagnostics />);
    act(() => useSelection.getState().setSchemaCheck(check({ schema_id: "other" })));
    expect(useSelection.getState().schemaCheck).toBeNull();
  });

  it("comes back for findings after it was dismissed, and is cleared with the schema", () => {
    render(<Diagnostics />);
    act(() => useSelection.getState().setDiagnosticsVisible(false));
    act(() => useSelection.getState().setSchemaCheck(check()));
    expect(useSelection.getState().diagnosticsVisible).toBe(true);
    act(() => useSelection.getState().setSchema("s2", alternativesModel));
    expect(useSelection.getState().schemaCheck).toBeNull();
  });
});
