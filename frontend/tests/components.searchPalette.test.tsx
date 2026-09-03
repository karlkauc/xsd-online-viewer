import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { SearchPalette } from "../src/components/SearchPalette";
import { useSelection } from "../src/stores/selectionStore";
import type { NodeIndexEntry } from "../src/types/schema";

function entry(id: string, label: string, node: object): NodeIndexEntry {
  return { id, kind: "element", label, qname: null, source_ref: null, node: node as never };
}

const INDEX: NodeIndexEntry[] = [
  entry("element:ISIN", "ISIN", { annotation: null }),
  entry("element:SecurityCode", "SecurityCode", {
    annotation: {
      documentation: [{ lang: "en", text: "International identifier such as the ISIN or the CUSIP of the share.", source: "documentation" }],
      appinfo: [],
      comments: [],
    },
  }),
  entry("element:Currency", "Currency", {
    annotation: null,
    type_inline_simple: { facets: [{ kind: "enumeration", value: "EUR", fixed: false }, { kind: "enumeration", value: "CHF", fixed: false }] },
  }),
];

function open() {
  act(() => window.dispatchEvent(new CustomEvent("xsdv:open-search")));
}

describe("SearchPalette", () => {
  afterEach(() => {
    cleanup();
    useSelection.setState({ index: [], selectedId: null });
  });

  it("finds documentation matches after name matches and shows the excerpt", async () => {
    useSelection.setState({ index: INDEX });
    render(<SearchPalette />);
    open();
    await userEvent.type(screen.getByPlaceholderText(/Search names/), "isin");
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("ISIN");
    expect(items[1]).toHaveTextContent("SecurityCode");
    expect(items[1]).toHaveTextContent(/such as the ISIN or the CUSIP/);
  });

  it("matches enumeration values and selects on Enter", async () => {
    useSelection.setState({ index: INDEX });
    render(<SearchPalette />);
    open();
    await userEvent.type(screen.getByPlaceholderText(/Search names/), "chf");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("listitem")).toHaveTextContent("Currency");
    await userEvent.keyboard("{Enter}");
    expect(useSelection.getState().selectedId).toBe("element:Currency");
  });
});
