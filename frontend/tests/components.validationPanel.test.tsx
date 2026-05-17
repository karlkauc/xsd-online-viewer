import { render, screen, act, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";
import type { ValidationResponse } from "../src/types/schema";

const validateXmlText = vi.fn();
const validateXmlFile = vi.fn();
const validateXmlUrl = vi.fn();

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    validateXmlText: (...a: unknown[]) => validateXmlText(...a),
    validateXmlFile: (...a: unknown[]) => validateXmlFile(...a),
    validateXmlUrl: (...a: unknown[]) => validateXmlUrl(...a),
  };
});

function openValidationTab() {
  render(<App />);
  act(() => {
    useSelection.getState().setSchema("test", smallModel);
  });
  act(() => {
    useSelection.getState().setActiveTab("validation");
  });
}

describe("ValidationPanel", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
    window.location.hash = "";
    validateXmlText.mockReset();
    validateXmlFile.mockReset();
    validateXmlUrl.mockReset();
  });

  afterEach(() => cleanup());

  it("shows a pass badge when the document is valid", async () => {
    const ok: ValidationResponse = {
      schema_id: "test",
      is_valid: true,
      reformatted_xml: "<?xml version='1.0'?>\n<Person/>\n",
      errors: [],
    };
    validateXmlText.mockResolvedValue(ok);
    openValidationTab();

    await userEvent.click(screen.getByRole("tab", { name: "Paste" }));
    await userEvent.type(
      screen.getByPlaceholderText("<root>…</root>"),
      "<Person/>",
    );
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(await screen.findByText(/Schema-valid/i)).toBeInTheDocument();
  });

  it("lists errors with ±1 line context and deep-links into the XSD", async () => {
    const ref = smallModel.complex_types[0];
    const bad: ValidationResponse = {
      schema_id: "test",
      is_valid: false,
      reformatted_xml: "<?xml version='1.0'?>\n<Person>\n  <Age>200</Age>\n</Person>\n",
      errors: [
        {
          line: 3,
          column: null,
          message: "The value '200' is greater than the maximum allowed.",
          severity: "error",
          type_name: "SCHEMAV_CVC_MAXINCLUSIVE_VALID",
          domain: "SCHEMASV",
          path: "/Person/Age",
          kind: "schema-validation",
          xsd_ref: {
            id: ref.id,
            file_id: "f1",
            line: ref.source_ref?.line ?? 1,
            qname: ref.name ?? "PersonType",
          },
        },
      ],
    };
    validateXmlText.mockResolvedValue(bad);
    openValidationTab();

    await userEvent.click(screen.getByRole("tab", { name: "Paste" }));
    await userEvent.type(
      screen.getByPlaceholderText("<root>…</root>"),
      "<Person><Age>200</Age></Person>",
    );
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(await screen.findByText(/1 error/i)).toBeInTheDocument();
    expect(
      screen.getByText(/greater than the maximum allowed/i),
    ).toBeInTheDocument();
    // ±1 window around line 3 => lines 2,3,4 rendered
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /View in XSD/i }),
    );
    await waitFor(() => {
      expect(useSelection.getState().activeTab).toBe("text");
      expect(useSelection.getState().selectedId).toBe(ref.id);
    });
  });

  it("explains when the input is not well-formed", async () => {
    const nwf: ValidationResponse = {
      schema_id: "test",
      is_valid: false,
      reformatted_xml: null,
      errors: [
        {
          line: 1,
          column: 12,
          message: "Premature end of data in tag Person",
          severity: "fatal",
          type_name: null,
          domain: null,
          path: null,
          kind: "not-well-formed",
          xsd_ref: null,
        },
      ],
    };
    validateXmlText.mockResolvedValue(nwf);
    openValidationTab();

    await userEvent.click(screen.getByRole("tab", { name: "Paste" }));
    await userEvent.type(
      screen.getByPlaceholderText("<root>…</root>"),
      "<Person>",
    );
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(
      await screen.findByText(/not well-formed XML/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Premature end of data/i),
    ).toBeInTheDocument();
  });
});
