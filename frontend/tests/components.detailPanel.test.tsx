import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { DetailPanel, FacetGroups } from "../src/components/DetailPanel";
import { useSelection } from "../src/stores/selectionStore";
import type { ComplexType, Facet, SchemaModel } from "../src/types/schema";
import { smallModel } from "./fixtures/smallModel";
import { refModel, SIGNATURE_ID, SIGNATURE_REF_ID } from "./fixtures/refModel";
import {
  assertionsModel,
  codeAttribute,
  codeElement,
  derivedAssertType,
  measurementElement,
} from "./fixtures/assertionsModel";
import {
  constraintsModel,
  libraryElement,
  bookElement,
  NS as CONSTRAINTS_NS,
} from "./fixtures/constraintsModel";
import {
  idRolesModel,
  uniqueIdElement,
  benchmarkRefElement,
  relatedRefsElement,
  plainElement,
  refAttribute,
} from "./fixtures/idRolesModel";

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

describe("DetailPanel element references", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("links a ref particle to the global declaration and shows its type", () => {
    act(() => {
      useSelection.getState().setSchema("ref", refModel);
      useSelection.getState().setSelected(SIGNATURE_REF_ID);
    });
    render(<DetailPanel />);
    expect(screen.getByText("References")).toBeInTheDocument();
    const link = screen.getByTitle("Go to element Signature");
    expect(link).toHaveTextContent("ds:Signature");
    expect(screen.getByText("ds:SignatureType")).toBeInTheDocument();

    act(() => link.click());
    expect(useSelection.getState().selectedId).toBe(SIGNATURE_ID);
  });
});

describe("DetailPanel assertions contributed by types", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("shows an element's named complex type's assertions with a 'from' label", () => {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(measurementElement.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText(/2 · XPath 2.0 · display-only/i)).toBeInTheDocument();
    expect(screen.getByText("MeasurementType")).toBeInTheDocument();
    expect(screen.getByText("xs:date(@from) le xs:date(@to)")).toBeInTheDocument();
    expect(screen.getByText("count(Value) gt 0")).toBeInTheDocument();
  });

  it("shows an element's named simple type's assertion with a 'from' label", () => {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(codeElement.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("PositiveCode")).toBeInTheDocument();
    expect(screen.getByText("string-length($value) gt 0")).toBeInTheDocument();
  });

  it("shows an attribute's named simple type's assertion with a 'from' label", () => {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(codeAttribute.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("PositiveCode")).toBeInTheDocument();
    expect(screen.getByText("string-length($value) gt 0")).toBeInTheDocument();
  });

  it("shows both levels of an extension chain when a complexType is selected directly", () => {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(derivedAssertType.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText(/2 · XPath 2.0 · display-only/i)).toBeInTheDocument();
    expect(screen.getByText("@derived-flag = 'ok'")).toBeInTheDocument();
    expect(screen.getByText("@base-flag = 'ok'")).toBeInTheDocument();
    expect(screen.getByText("BaseAssertType")).toBeInTheDocument();
  });
});

describe("DetailPanel identity constraints", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("shows the Library element's four identity constraints", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(libraryElement.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("Identity constraints")).toBeInTheDocument();
    expect(
      screen.getByText(/4 · xs:key \/ xs:keyref \/ xs:unique · display-only/i),
    ).toBeInTheDocument();
    expect(screen.getByText("bookKey")).toBeInTheDocument();
    expect(screen.getByText("uniqueTitle")).toBeInTheDocument();
    expect(screen.getByText("loanBookRef")).toBeInTheDocument();
    expect(screen.getByText("danglingRef")).toBeInTheDocument();
  });

  it("shows a nested element's own constraint (Loans -> loanKey)", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(`element:{${CONSTRAINTS_NS}}Loans`);
    });
    render(<DetailPanel />);
    expect(screen.getByText("Identity constraints")).toBeInTheDocument();
    expect(screen.getByText("loanKey")).toBeInTheDocument();
  });

  it("does not show the section for an element without constraints", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(bookElement.id);
    });
    render(<DetailPanel />);
    expect(screen.queryByText("Identity constraints")).not.toBeInTheDocument();
  });

  it("clicking a resolved selector step selects that element", async () => {
    const user = userEvent.setup();
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(libraryElement.id);
    });
    render(<DetailPanel />);
    const [bookStep] = screen.getAllByRole("button", { name: "tns:Book" });
    await user.click(bookStep);
    expect(useSelection.getState().selectedId).toBe(bookElement.id);
  });
});

describe("DetailPanel ID/IDREF", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("shows an IDREF chip and the ID reference section for an idref element", () => {
    act(() => {
      useSelection.getState().setSchema("idroles", idRolesModel);
      useSelection.getState().setSelected(benchmarkRefElement.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("ID role")).toBeInTheDocument();
    expect(screen.getByText("IDREF")).toBeInTheDocument();
    expect(screen.getByText("ID reference")).toBeInTheDocument();
    expect(
      screen.getByText(/does not bind an IDREF to a specific ID/),
    ).toBeInTheDocument();
    expect(screen.getByText("UniqueID")).toBeInTheDocument();
  });

  it("shows an IDREFS chip for an idrefs element", () => {
    act(() => {
      useSelection.getState().setSchema("idroles", idRolesModel);
      useSelection.getState().setSelected(relatedRefsElement.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("IDREFS")).toBeInTheDocument();
    expect(screen.getByText("ID reference")).toBeInTheDocument();
  });

  it("shows 'Referenced by IDREF' with usage rows for an xs:ID element", () => {
    act(() => {
      useSelection.getState().setSchema("idroles", idRolesModel);
      useSelection.getState().setSelected(uniqueIdElement.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("ID role")).toBeInTheDocument();
    expect(screen.getByText("Referenced by IDREF")).toBeInTheDocument();
    expect(screen.getByText("BenchmarkRef")).toBeInTheDocument();
    expect(screen.getByText("RelatedRefs")).toBeInTheDocument();
    expect(screen.getByText("refAttr")).toBeInTheDocument();
  });

  it("shows the IDREF chip and ID reference section for an idref attribute", () => {
    act(() => {
      useSelection.getState().setSchema("idroles", idRolesModel);
      useSelection.getState().setSelected(refAttribute.id);
    });
    render(<DetailPanel />);
    expect(screen.getByText("ID role")).toBeInTheDocument();
    expect(screen.getByText("IDREF")).toBeInTheDocument();
    expect(screen.getByText("ID reference")).toBeInTheDocument();
  });

  it("does not show ID role or ID/IDREF sections for a plain element", () => {
    act(() => {
      useSelection.getState().setSchema("idroles", idRolesModel);
      useSelection.getState().setSelected(plainElement.id);
    });
    render(<DetailPanel />);
    expect(screen.queryByText("ID role")).not.toBeInTheDocument();
    expect(screen.queryByText("ID reference")).not.toBeInTheDocument();
    expect(screen.queryByText("Referenced by IDREF")).not.toBeInTheDocument();
  });

  it("caps xs:ID candidates at 8 with a 'Show all (9)' button that reveals the 9th", async () => {
    const user = userEvent.setup();
    function makeIdElement(i: number) {
      return {
        id: `element:{urn:capmodel}Id${i}`,
        name: `Id${i}`,
        qname: `{urn:capmodel}Id${i}`,
        ref: null,
        type_name: "xs:ID",
        type_inline_simple: null,
        type_inline_complex: null,
        min_occurs: 1,
        max_occurs: 1,
        default: null,
        fixed: null,
        nillable: false,
        abstract: false,
        substitution_group: null,
        form: "qualified" as const,
        target_namespace: "urn:capmodel",
        is_global: true,
        annotation: null,
        source_ref: { file_id: "f1", line: 10 + i },
        id_role: "id" as const,
      };
    }
    const capIdElements = Array.from({ length: 9 }, (_, i) => makeIdElement(i));
    const capRefElement = {
      id: "element:{urn:capmodel}Ref",
      name: "Ref",
      qname: "{urn:capmodel}Ref",
      ref: null,
      type_name: "xs:IDREF",
      type_inline_simple: null,
      type_inline_complex: null,
      min_occurs: 1,
      max_occurs: 1,
      default: null,
      fixed: null,
      nillable: false,
      abstract: false,
      substitution_group: null,
      form: "qualified" as const,
      target_namespace: "urn:capmodel",
      is_global: true,
      annotation: null,
      source_ref: { file_id: "f1", line: 1 },
      id_role: "idref" as const,
    };
    const capModel: SchemaModel = {
      schema_id: "cap-test",
      target_namespace: "urn:capmodel",
      namespaces: {},
      element_form_default: "qualified",
      attribute_form_default: "qualified",
      elements: [capRefElement, ...capIdElements],
      attributes: [],
      simple_types: [],
      complex_types: [],
      groups: [],
      attribute_groups: [],
      files: [
        {
          id: "f1",
          filename: "cap.xsd",
          target_namespace: "urn:capmodel",
          relationship: "main",
          content: null,
        },
      ],
      diagnostics: [],
    };
    act(() => {
      useSelection.getState().setSchema("cap", capModel);
      useSelection.getState().setSelected(capRefElement.id);
    });
    render(<DetailPanel />);
    for (let i = 0; i < 8; i++) {
      expect(screen.getByText(`Id${i}`)).toBeInTheDocument();
    }
    expect(screen.queryByText("Id8")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all (9)" }));
    expect(screen.getByText("Id8")).toBeInTheDocument();
  });
});
