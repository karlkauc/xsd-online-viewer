import { render, screen, act } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DetailPanel, FacetGroups } from "../src/components/DetailPanel";
import { useSelection } from "../src/stores/selectionStore";
import type { ComplexType, Facet, SchemaModel } from "../src/types/schema";
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

  it("does not render an 'Overridden by' self-badge on an override replacement", () => {
    const originalCt: ComplexType = {
      id: "complexType:{http://example.com/ovr}ColorType",
      name: "ColorType",
      anonymous: false,
      abstract: false,
      mixed: false,
      content_kind: "complex",
      derivation: "none",
      base: null,
      particle: null,
      attributes: [],
      attribute_group_refs: [],
      simple_content_base: null,
      simple_content_facets: [],
      annotation: null,
      source_ref: { file_id: "f-base", line: 4 },
    };
    const replacementCt: ComplexType = {
      ...originalCt,
      id: "override:f-ovr#complexType:{http://example.com/ovr}ColorType",
      source_ref: { file_id: "f-ovr", line: 7 },
    };
    const overrideModel: SchemaModel = {
      ...smallModel,
      elements: [],
      simple_types: [],
      complex_types: [originalCt, replacementCt],
      overrides: [
        {
          target_file_id: "f-base",
          source_ref: { file_id: "f-ovr", line: 5 },
          replacements: [
            {
              kind: "complexType",
              // Backend records the qname using ComplexType.name (local) —
              // matches what buildIndex puts on entry.qname.
              qname: "ColorType",
              replacement_id: replacementCt.id,
              source_ref: { file_id: "f-ovr", line: 7 },
            },
          ],
        },
      ],
    };
    act(() => {
      useSelection.getState().setSchema("ovr", overrideModel);
      useSelection.getState().setSelected(replacementCt.id);
    });
    render(<DetailPanel />);
    // The replacement IS a replacement → "overrides …" badge should appear.
    expect(
      screen.getByRole("button", {
        name: /This is a replacement for complexType/i,
      }),
    ).toBeInTheDocument();
    // …but it must NOT also show "Overridden by" pointing at itself.
    expect(
      screen.queryByRole("button", { name: /Overridden by/i }),
    ).not.toBeInTheDocument();
  });

  it("shows 'Overridden by' badge on the original when a replacement exists", () => {
    const originalCt: ComplexType = {
      id: "complexType:{http://example.com/ovr}ColorType",
      name: "ColorType",
      anonymous: false,
      abstract: false,
      mixed: false,
      content_kind: "complex",
      derivation: "none",
      base: null,
      particle: null,
      attributes: [],
      attribute_group_refs: [],
      simple_content_base: null,
      simple_content_facets: [],
      annotation: null,
      source_ref: { file_id: "f-base", line: 4 },
    };
    const replacementCt: ComplexType = {
      ...originalCt,
      id: "override:f-ovr#complexType:{http://example.com/ovr}ColorType",
      source_ref: { file_id: "f-ovr", line: 7 },
    };
    const overrideModel: SchemaModel = {
      ...smallModel,
      elements: [],
      simple_types: [],
      complex_types: [originalCt, replacementCt],
      overrides: [
        {
          target_file_id: "f-base",
          source_ref: { file_id: "f-ovr", line: 5 },
          replacements: [
            {
              kind: "complexType",
              // Backend records the qname using ComplexType.name (local) —
              // matches what buildIndex puts on entry.qname.
              qname: "ColorType",
              replacement_id: replacementCt.id,
              source_ref: { file_id: "f-ovr", line: 7 },
            },
          ],
        },
      ],
    };
    act(() => {
      useSelection.getState().setSchema("ovr", overrideModel);
      useSelection.getState().setSelected(originalCt.id);
    });
    render(<DetailPanel />);
    expect(
      screen.getByRole("button", { name: /Overridden by/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /This is a replacement for/i,
      }),
    ).not.toBeInTheDocument();
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
