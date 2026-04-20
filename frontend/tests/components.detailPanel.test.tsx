import { render, screen, act } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DetailPanel, FacetGroups } from "../src/components/DetailPanel";
import { useSelection } from "../src/stores/selectionStore";
import type { Facet } from "../src/types/schema";
import { smallModel } from "./fixtures/smallModel";

describe("DetailPanel", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("prompts when nothing is selected", () => {
    render(<DetailPanel />);
    expect(screen.getByText(/select a node/i)).toBeInTheDocument();
  });

  it("renders grouped facets for a selected simpleType", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection
        .getState()
        .setSelected("simpleType:{http://example.com/simple}AgeType");
    });
    render(<DetailPanel />);
    expect(screen.getByRole("heading", { name: "AgeType" })).toBeInTheDocument();
    expect(screen.getByText("Range")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
  });

  it("resolves and renders facets when an element referring to a named simpleType is selected", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection
        .getState()
        .setSelected("element:{http://example.com/simple}PersonType/Age");
    });
    render(<DetailPanel />);
    expect(screen.getByRole("heading", { name: "Age" })).toBeInTheDocument();
    expect(screen.getByText("Range")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
    expect(screen.getByText(/inherited from/)).toBeInTheDocument();
    expect(screen.getByText("AgeType")).toBeInTheDocument();
  });
});

describe("FacetGroups", () => {
  it("groups facets by category and renders headers in order", () => {
    const facets: Facet[] = [
      { kind: "minInclusive", value: "1", fixed: false, annotation: null },
      { kind: "maxInclusive", value: "9999", fixed: false, annotation: null },
      { kind: "enumeration", value: "LOW", fixed: false, annotation: null },
      { kind: "enumeration", value: "HIGH", fixed: false, annotation: null },
      { kind: "pattern", value: "[A-Z]+", fixed: false, annotation: null },
    ];
    render(<FacetGroups facets={facets} restriction={null} />);

    // Group order: enumeration → range → pattern. The Enumeration header
    // includes a "· N values" meta suffix; match by prefix instead.
    const headers = screen.getAllByText(/^(Enumeration|Range|Pattern)/);
    const titles = headers.map((h) =>
      (h.textContent ?? "").replace(/·.*$/, "").trim(),
    );
    expect(titles).toEqual(["Enumeration", "Range", "Pattern"]);

    expect(screen.getByText("LOW")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("9999")).toBeInTheDocument();
    expect(screen.getByText("[A-Z]+")).toBeInTheDocument();
  });

  it("shows inherited label when provided", () => {
    render(
      <FacetGroups
        facets={[{ kind: "pattern", value: ".+", fixed: false, annotation: null }]}
        restriction={null}
        inheritedFrom="CurrencyCode"
      />,
    );
    expect(screen.getByText(/inherited from/)).toBeInTheDocument();
    expect(screen.getByText("CurrencyCode")).toBeInTheDocument();
  });
});
