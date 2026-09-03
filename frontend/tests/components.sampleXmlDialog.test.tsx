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

function respondWith(text: string) {
  fetchMock.mockResolvedValue({ ok: true, status: 200, text: async () => text });
}

describe("SampleXmlDialog", () => {
  it("stays closed until asked, then fetches and shows the sample", async () => {
    respondWith("<Person>\n  <FirstName>string</FirstName>\n</Person>");
    render(<SampleXmlDialog />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    act(() => openSampleXml({ elementId: "element:{ns}Person", name: "Person" }));
    expect(screen.getByRole("dialog", { name: "Sample XML for <Person>" })).toBeInTheDocument();
    expect(await screen.findByText(/<FirstName>string<\/FirstName>/)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/schema/abc/sample?element=element%3A%7Bns%7DPerson");
  });

  it("refetches with optional content when the checkbox is toggled", async () => {
    respondWith("<Person/>");
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await screen.findByText("<Person/>");
    await userEvent.click(screen.getByRole("checkbox", { name: /Include optional/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toContain("optional=true");
  });

  it("copies the XML to the clipboard", async () => {
    respondWith("<Person/>");
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await screen.findByText("<Person/>");
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("<Person/>");
    expect(await screen.findByText("Copied ✓")).toBeInTheDocument();
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
