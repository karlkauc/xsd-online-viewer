import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SampleXmlDialog, openSampleXml } from "../src/components/SampleXmlDialog";
import { useSelection } from "../src/stores/selectionStore";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  useSelection.setState({ schemaId: "abc" });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sampleText = () => document.querySelector('[data-testid="sample-xml"] .cm-content')?.textContent ?? "";
const waitForSample = (fragment: string) => waitFor(() => expect(sampleText()).toContain(fragment));

const VALID = { schema_id: "abc", is_valid: true, reformatted_xml: "", errors: [] };

function respondWith(text: string, validation: object = VALID) {
  fetchMock.mockImplementation(async (url: string) =>
    String(url).includes("/validate/")
      ? { ok: true, status: 200, json: async () => validation }
      : { ok: true, status: 200, text: async () => text },
  );
}

const sampleCalls = () => fetchMock.mock.calls.filter((c) => !String(c[0]).includes("/validate/"));

describe("SampleXmlDialog", () => {
  it("stays closed until asked, then fetches and shows the sample", async () => {
    respondWith("<Person>\n  <FirstName>string</FirstName>\n</Person>");
    render(<SampleXmlDialog />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    act(() => openSampleXml({ elementId: "element:{ns}Person", name: "Person" }));
    expect(screen.getByRole("dialog", { name: "Sample XML for <Person>" })).toBeInTheDocument();
    await waitForSample("<FirstName>string</FirstName>");
    expect(sampleCalls()[0][0]).toBe("/api/schema/abc/sample?element=element%3A%7Bns%7DPerson");
    expect(await screen.findByRole("status")).toHaveTextContent("Schema-valid");
    expect(screen.getByRole("link", { name: "FreeXmlToolkit ↗" })).toHaveAttribute("href", "/go/freexmltoolkit");
  });

  it("reports validation errors and hands them to the Validation tab", async () => {
    const invalid = {
      schema_id: "abc",
      is_valid: false,
      reformatted_xml: "<Person/>",
      errors: [{ line: 2, column: 1, message: "Missing child element(s). Expected is ( Name ).", severity: "error" }],
    };
    respondWith("<Person/>", invalid);
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    const status = await screen.findByRole("status");
    await waitFor(() => expect(status).toHaveTextContent("Not schema-valid: 1 validation error"));
    expect(status).toHaveTextContent("line 2: Missing child element(s)");
    await userEvent.click(screen.getByRole("button", { name: "Show in Validation tab" }));
    expect(useSelection.getState().activeTab).toBe("validation");
    expect(useSelection.getState().validationResult?.errors).toHaveLength(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("refetches with optional content when the checkbox is toggled", async () => {
    respondWith("<Person/>");
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await waitForSample("<Person/>");
    await userEvent.click(screen.getByRole("checkbox", { name: /Include optional/ }));
    await waitFor(() => expect(sampleCalls()).toHaveLength(2));
    expect(sampleCalls()[1][0]).toContain("optional=true");
  });

  it("copies the XML to the clipboard", async () => {
    respondWith("<Person/>");
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await waitForSample("<Person/>");
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("<Person/>");
    expect(await screen.findByText("Copied ✓")).toBeInTheDocument();
  });

  it("lets the user switch between candidate roots", async () => {
    respondWith("<X/>");
    render(<SampleXmlDialog />);
    act(() =>
      openSampleXml({
        elementId: "element:A",
        name: "A",
        candidates: [
          { elementId: "element:A", name: "A" },
          { elementId: "element:B", name: "B" },
        ],
      }),
    );
    await waitForSample("<X/>");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Root element/ }), "element:B");
    expect(screen.getByRole("dialog", { name: "Sample XML for <B>" })).toBeInTheDocument();
    await waitFor(() => expect(sampleCalls()).toHaveLength(2));
    expect(sampleCalls()[1][0]).toContain("element=element%3AB");
  });

  it("shows the backend error and closes on Escape", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "element not found in schema" }) });
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Nope", name: "Nope" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("element not found in schema");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
