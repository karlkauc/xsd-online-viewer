import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
    too_large: false,
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

  describe("a schema too large to be checked unasked", () => {
    const tooLarge = check({ status: "not_checked", findings: [], too_large: true });

    afterEach(() => vi.unstubAllGlobals());

    function answerWith(body: SchemaCheckResponse | null) {
      const fetchMock = vi.fn(async (_url: string) =>
        body ? new Response(JSON.stringify(body)) : new Response("", { status: 503 }),
      );
      vi.stubGlobal("fetch", fetchMock);
      return fetchMock;
    }

    it("offers the check and says when it found nothing", async () => {
      const fetchMock = answerWith(check({ status: "ok", findings: [] }));
      render(<Diagnostics />);
      act(() => useSelection.getState().setSchemaCheck(tooLarge));
      expect(screen.getByText("Schema check")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Check now" }));
      expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/schema\/s1\/check\?large=true$/);
      expect(await screen.findByText(/breaks no rule of XSD 1\.0/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Check now" })).toBeNull();
    });

    it("lists what the check found", async () => {
      answerWith(check());
      render(<Diagnostics />);
      act(() => useSelection.getState().setSchemaCheck(tooLarge));
      await userEvent.click(screen.getByRole("button", { name: "Check now" }));
      expect(await screen.findByText("the derived group is an illegal restriction")).toBeInTheDocument();
      expect(screen.queryByTestId("schema-check-on-demand")).toBeNull();
    });

    it("says why a check did not finish and lets it be tried again", async () => {
      answerWith(check({ status: "not_checked", findings: [], detail: "the check took longer than 50 s" }));
      render(<Diagnostics />);
      act(() => useSelection.getState().setSchemaCheck(tooLarge));
      await userEvent.click(screen.getByRole("button", { name: "Check now" }));
      expect(await screen.findByText(/did not finish: the check took longer than 50 s/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    });

    it("keeps the offer when the server does not answer", async () => {
      answerWith(null);
      render(<Diagnostics />);
      act(() => useSelection.getState().setSchemaCheck(tooLarge));
      await userEvent.click(screen.getByRole("button", { name: "Check now" }));
      expect(await screen.findByText("The check did not finish.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    });
  });
});
