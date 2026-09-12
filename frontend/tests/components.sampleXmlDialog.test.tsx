import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SampleXmlDialog, openSampleXml } from "../src/components/SampleXmlDialog";
import { useSelection } from "../src/stores/selectionStore";
import type { SchemaModel } from "../src/types/schema";

const fetchMock = vi.fn();

// The dialog validates samples only for document roots. With no "main" file
// in the model every global element counts as a root (see computeRootElements),
// so a bare element list is enough to mark these ids as roots.
const ROOT_IDS = ["element:{ns}Person", "element:Person", "element:A", "element:B"];
const MODEL = {
  schema_id: "abc",
  target_namespace: null,
  namespaces: {},
  element_form_default: "unqualified",
  attribute_form_default: "unqualified",
  elements: ROOT_IDS.map((id) => ({ id, name: id.split(/[}:]/).pop() })),
  attributes: [],
  simple_types: [],
  complex_types: [],
  groups: [],
  attribute_groups: [],
  files: [],
  diagnostics: [],
} as unknown as SchemaModel;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  useSelection.setState({ schemaId: "abc", model: MODEL });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sampleText = () => document.querySelector('[data-testid="sample-xml"] .cm-content')?.textContent ?? "";
const waitForSample = (fragment: string) => waitFor(() => expect(sampleText()).toContain(fragment));

const VALID = { schema_id: "abc", is_valid: true, reformatted_xml: "", errors: [] };

function respondWith(text: string, validation: object = VALID, report: string | null = null) {
  fetchMock.mockImplementation(async (url: string) =>
    String(url).includes("/validate/")
      ? { ok: true, status: 200, json: async () => validation }
      : {
          ok: true,
          status: 200,
          text: async () => text,
          // The generator report travels in a header (see fetchSampleXml).
          headers: new Headers(report ? { "X-Sample-Report": report } : {}),
        },
  );
}

const sampleCalls = () => fetchMock.mock.calls.filter((c) => !String(c[0]).includes("/validate/"));
const validateCalls = () => fetchMock.mock.calls.filter((c) => String(c[0]).includes("/validate/"));

/** A sample that names the element and option it was generated for. */
const parameterSample = (elementId: string | null, optional: boolean) =>
  `<Sample element="${elementId}" optional="${optional}"/>`;

function respondWithParameters() {
  fetchMock.mockImplementation(async (url: string) => {
    if (String(url).includes("/validate/")) return { ok: true, status: 200, json: async () => VALID };
    const params = new URL(String(url), "http://localhost").searchParams;
    const text = parameterSample(params.get("element"), params.get("optional") === "true");
    return { ok: true, status: 200, text: async () => text, headers: new Headers() };
  });
}

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

  it("hands the generator report to the validation request", async () => {
    // The report is what lets the backend tell a generator bug apart from a
    // broken schema, so it has to survive the round trip untouched.
    respondWith("<Person/>", VALID, "eyJjb3VudHMiOnt9fQ==");
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await screen.findByRole("status");

    const validateCall = fetchMock.mock.calls.find((c) => String(c[0]).includes("/validate/"));
    expect(validateCall).toBeDefined();
    const body = JSON.parse(String(validateCall![1].body));
    expect(body.origin).toBe("sample");
    expect(body.sample).toMatchObject({
      element_id: "element:Person",
      include_optional: false,
      report: "eyJjb3VudHMiOnt9fQ==",
    });
    expect(body.sample.generation_ms).toBeGreaterThanOrEqual(0);
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

  it("does not validate a nested element's sample and says it is a fragment", async () => {
    respondWith("<Address/>");
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Address", name: "Address" }));
    await waitForSample("<Address/>");
    expect(await screen.findByTestId("sample-fragment-note")).toHaveTextContent(
      "Fragment only — <Address> is not a document root",
    );
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).includes("/validate/"))).toHaveLength(0);
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

  // The check says how the sample was made, and a failing one is recorded in
  // sample_issue under exactly that. Checking the previous sample under a new
  // element or option records a defect that never happened (UBL, A-GRA).
  it("never validates the previous element's sample under the new element", async () => {
    respondWithParameters();
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Address", name: "Address" }));
    await screen.findByTestId("sample-fragment-note");
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await screen.findByText(/Schema-valid/);

    expect(validateCalls().length).toBeGreaterThan(0);
    for (const [, init] of validateCalls()) {
      const body = JSON.parse(String(init.body));
      expect(body.content).toBe(parameterSample(body.sample.element_id, body.sample.include_optional));
    }
  });

  it("never validates the required-only sample as the one with optional content", async () => {
    respondWithParameters();
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    await screen.findByText(/Schema-valid/);
    await userEvent.click(screen.getByRole("checkbox", { name: /Include optional/ }));
    await waitFor(() =>
      expect(validateCalls().some(([, init]) => JSON.parse(String(init.body)).sample.include_optional)).toBe(true),
    );

    for (const [, init] of validateCalls()) {
      const body = JSON.parse(String(init.body));
      expect(body.content).toBe(parameterSample(body.sample.element_id, body.sample.include_optional));
    }
  });

  // A schema that references declarations it never loaded cannot compile, so
  // the check would only fail with a compiler message (UBL without its imports).
  it("skips the check for an incomplete schema and says what is missing", async () => {
    useSelection.setState({
      model: {
        ...MODEL,
        diagnostics: [
          {
            severity: "warning",
            message: "invoice.xsd: unresolved import schemaLocation='common/cac.xsd'",
            file_id: null,
            line: 3,
          },
        ],
      } as SchemaModel,
    });
    const missing = encodeURIComponent(JSON.stringify({ count: 7, names: ["cac:Party", "cbc:ID"] }));
    fetchMock.mockImplementation(async (url: string) =>
      String(url).includes("/validate/")
        ? { ok: true, status: 200, json: async () => VALID }
        : { ok: true, status: 200, text: async () => "<Invoice/>", headers: new Headers({ "X-Sample-Missing": missing }) },
    );
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));

    const note = await screen.findByTestId("sample-incomplete-note");
    expect(note).toHaveTextContent(
      "Not validated — the schema is incomplete: 7 referenced declarations are missing from the loaded files (cac:Party, cbc:ID, …).",
    );
    expect(note).toHaveTextContent("Not loaded: common/cac.xsd");
    expect(validateCalls()).toHaveLength(0);
  });

  it("explains a check the server refuses because the schema does not compile", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      String(url).includes("/validate/")
        ? {
            ok: false,
            status: 422,
            json: async () => ({
              detail:
                "the schema itself is not valid XSD: a.xsd line 4: Element '{...}complexType': The content is not valid.",
            }),
          }
        : { ok: true, status: 200, text: async () => "<Person/>", headers: new Headers() },
    );
    render(<SampleXmlDialog />);
    act(() => openSampleXml({ elementId: "element:Person", name: "Person" }));
    expect(
      await screen.findByText(
        "Cannot check the sample: the schema itself is not valid XSD: a.xsd line 4: " +
          "Element '{...}complexType': The content is not valid.",
      ),
    ).toBeInTheDocument();
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
